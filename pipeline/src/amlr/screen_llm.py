"""Three-LLM reviewer panel for title/abstract and full-text screening (PROTOCOL §6)."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Callable

from .config import REPO_ROOT
from .gateway import RRZEClientError, Transport
from .llm import PANEL, chat, client_for, parse_json_object
from .schema import Decision, PrismaPhase, Stage
from .storage import locked, read_jsonl, rewrite_jsonl

PROMPT_FILE = REPO_ROOT / "protocol" / "screening_prompt.md"
SCREENING_DIR = REPO_ROOT / "data" / "screening"
REASON_PRECEDENCE = ("E5", "E4", "E6", "E1", "E2", "E3")
_SPLIT = "<!-- RECORD TEMPLATE -->"
# Keeps full-text prompts well inside the context window of every panel model.
MAX_FULLTEXT_CHARS = 60_000
# Reasoning models spend most of their budget thinking before the JSON answer.
MAX_TOKENS = 8192

_ELIGIBLE = {
    Stage.title_abstract: {PrismaPhase.identified.value},
    Stage.full_text: {PrismaPhase.screened_in.value, PrismaPhase.fulltext_sought.value,
                      PrismaPhase.assessed.value},
}


def load_prompt(path: Path = PROMPT_FILE) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8")
    system, template = text.split(_SPLIT, 1)
    return system.strip(), template.strip(), hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_record(template: str, record: dict, stage: Stage, full_text: str | None = None) -> str:
    if stage is Stage.title_abstract:
        label, body = "Abstract", record.get("abstract") or "(no abstract available)"
    elif record.get("assessment_basis") == "abstract_only":
        # Full text could not be obtained; the panel judges eligibility on the abstract alone.
        label, body = "Abstract only (full text unavailable)", record.get("abstract") or ""
    else:
        label, body = "Full text", (full_text or "")[:MAX_FULLTEXT_CHARS]
    return template.format(
        stage=stage.value,
        title=record.get("title") or "",
        year=record.get("year") or "unknown",
        venue=record.get("venue") or "unknown",
        keywords=", ".join(record.get("keywords") or []) or "-",
        body_label=label,
        body=body,
    )


def _norm_reason(value) -> str | None:
    code = str(value or "").strip().upper()
    return code if code in REASON_PRECEDENCE else None


def cast_vote(reviewer: str, model: str, system: str, user: str, prompt_sha: str,
              record_id: str, stage: Stage, transport: Transport | None = None) -> dict:
    row = {
        "record_id": record_id, "stage": stage.value, "reviewer": reviewer,
        "model": model, "prompt_sha256": prompt_sha,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "include": None, "reason": None, "confidence": None, "rationale": None,
        "model_reported": None, "finish_reason": None, "raw": None, "error": None,
        "elapsed_s": None, "usage": None,
    }
    t0 = time.monotonic()
    try:
        resp = chat(client_for(model, transport=transport), system, user, max_tokens=MAX_TOKENS)
        row.update(model_reported=resp.model, finish_reason=resp.finish_reason, raw=resp.content,
                   usage=resp.raw.get("usage"))
        obj = parse_json_object(resp.content, "decision")
        include = str(obj.get("decision", "")).strip().lower() == "include"
        row.update(
            include=include,
            reason=None if include else (_norm_reason(obj.get("reason")) or "unspecified"),
            confidence=obj.get("confidence"),
            rationale=obj.get("rationale"),
        )
    except (RRZEClientError, ValueError) as e:
        row["error"] = f"{type(e).__name__}: {e}"[:500]
    row["elapsed_s"] = round(time.monotonic() - t0, 2)
    return row


def aggregate(votes: list[dict], *, liberal: bool = False) -> dict:
    """Majority rule (≥ 2 of 3 include). `liberal`: any include suffices (no-abstract records)."""

    n_inc = sum(1 for v in votes if v["include"])
    include = n_inc >= 1 if liberal else n_inc >= 2
    reason = None
    if not include:
        codes = [v["reason"] for v in votes if not v["include"] and v["reason"]]
        counts = Counter(codes)
        top = [c for c, k in counts.items() if k == max(counts.values())] if counts else []
        rank = {c: i for i, c in enumerate(REASON_PRECEDENCE)}
        reason = min(top, key=lambda c: rank.get(c, len(rank))) if top else "unspecified"
    return {"include": include, "votes": f"{n_inc}/{len(votes)}", "reason": reason}


def _ledger_path(stage: Stage) -> Path:
    return SCREENING_DIR / f"{stage.value}-votes.jsonl"


def _valid_votes(ledger: list[dict], stage: Stage, sha: str) -> dict[str, dict[str, dict]]:
    """record_id → reviewer → latest valid vote, for this stage and prompt version."""

    out: dict[str, dict[str, dict]] = {}
    for v in ledger:
        if v["stage"] != stage.value:
            continue
        if "invalidated_at" in v:  # input text withdrawn: earlier votes on this record no longer count
            out.pop(v["record_id"], None)
        elif v["prompt_sha256"] == sha and v["include"] is not None:
            out.setdefault(v["record_id"], {})[v["reviewer"]] = v
    return out


PRIMARY = ("R1", "R2")
TIEBREAK = "R3"
# Share of records on which R3 votes even when R1 and R2 agree, to estimate 3-rater agreement.
AUDIT_FRACTION = 0.10


def in_audit(record_id: str, fraction: float = AUDIT_FRACTION) -> bool:
    """Deterministic pseudo-random audit membership, stable across runs and machines."""

    return int(hashlib.sha256(record_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < fraction


def needs_tiebreak(votes: dict[str, dict], record: dict, stage: Stage) -> bool:
    """True when R3's vote could change the 2-of-3 outcome or the majority exclusion reason."""

    a, b = votes[PRIMARY[0]], votes[PRIMARY[1]]
    if a["include"] != b["include"]:
        return True
    # PRISMA 2020 reports exclusion reasons only for full-text reports, so at title/abstract a
    # reason-code disagreement is settled by precedence (see `aggregate`) instead of by R3.
    if stage is Stage.full_text and not a["include"] and a["reason"] != b["reason"]:
        return True
    # No-abstract records pass on a single include, so two excludes are not yet decisive.
    return stage is Stage.title_abstract and not record.get("abstract") and not a["include"]


def _decidable(votes: dict[str, dict], record: dict, stage: Stage) -> bool:
    if set(PANEL) <= set(votes):
        return True
    return set(PRIMARY) <= set(votes) and not needs_tiebreak(votes, record, stage)


def _execute(tasks, system, sha, stage, transport, workers, fh) -> int:
    errors = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(cast_vote, rv, PANEL[rv], system, user, sha, r["id"], stage, transport): (r, rv)
                   for r, rv, user in tasks}
        for f in as_completed(futures):
            try:
                row = f.result()
            except Exception as e:  # never let one failed vote end the run; it is retried next pass
                r, rv = futures[f]
                row = {"record_id": r["id"], "stage": stage.value, "reviewer": rv, "model": PANEL[rv],
                       "prompt_sha256": sha, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "include": None, "reason": None, "error": f"{type(e).__name__}: {e}"[:500]}
            errors += row["error"] is not None
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
    return errors


def run_panel(
    stage: Stage,
    corpus_path: Path,
    *,
    mode: str = "adaptive",
    audit: bool = True,
    limit: int | None = None,
    workers: int = 3,
    tiebreak_workers: int = 4,
    full_text_for: Callable[[dict], str | None] | None = None,
    transport: Transport | None = None,
    ledger_path: Path | None = None,
    prompt_path: Path = PROMPT_FILE,
) -> dict:
    """Collect missing votes for eligible records, then apply panel decisions to the corpus.

    mode="adaptive": R1 and R2 vote on every record; R3 votes only where it can change the
    majority outcome or reason (plus the audit sample). Decisions equal those of a full
    three-vote majority. mode="full": all three vote on every record.
    """

    if mode not in ("adaptive", "full"):
        raise ValueError(mode)
    system, template, sha = load_prompt(prompt_path)
    ledger_path = ledger_path or _ledger_path(stage)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    first = PANEL if mode == "full" else PRIMARY

    records, prompts, skipped_no_text = [], {}, 0
    done = _valid_votes(read_jsonl(ledger_path), stage, sha)
    for r in read_jsonl(corpus_path):
        if r.get("phase", PrismaPhase.identified.value) not in _ELIGIBLE[stage]:
            continue
        text = None
        if stage is Stage.full_text:
            text = full_text_for(r) if full_text_for else None
            if not text:
                skipped_no_text += 1
                continue
        if _decidable(done.get(r["id"], {}), r, stage) and not (mode == "adaptive" and audit and in_audit(r["id"])
                                                                   and TIEBREAK not in done.get(r["id"], {})):
            continue
        records.append(r)
        prompts[r["id"]] = render_record(template, r, stage, text)
        if limit is not None and len(records) >= limit:
            break

    with ledger_path.open("a", encoding="utf-8") as fh:
        round1 = [(r, rv, prompts[r["id"]]) for r in records for rv in first if rv not in done.get(r["id"], {})]
        errors = _execute(round1, system, sha, stage, transport, workers, fh)
        round2, early = [], 0
        if mode == "adaptive":
            fh.flush()
            # Apply what R1/R2 already settle, so slow tie-breaks do not hold back the rest.
            early = apply_decisions(stage, corpus_path, ledger_path, sha)
            done = _valid_votes(read_jsonl(ledger_path), stage, sha)
            for r in records:
                v = done.get(r["id"], {})
                if TIEBREAK in v or not set(PRIMARY) <= set(v):
                    continue
                if needs_tiebreak(v, r, stage) or (audit and in_audit(r["id"])):
                    round2.append((r, TIEBREAK, prompts[r["id"]]))
            errors += _execute(round2, system, sha, stage, transport, tiebreak_workers, fh)

    applied = early + apply_decisions(stage, corpus_path, ledger_path, sha)
    return {"mode": mode, "votes_cast": len(round1) + len(round2), "tiebreak_or_audit_votes": len(round2),
            "vote_errors": errors, "decided": applied, "skipped_no_full_text": skipped_no_text,
            "prompt_sha256": sha}


def apply_decisions(stage: Stage, corpus_path: Path, ledger_path: Path, sha: str) -> int:
    with locked(corpus_path):
        return _apply_decisions(stage, corpus_path, ledger_path, sha)


def _apply_decisions(stage: Stage, corpus_path: Path, ledger_path: Path, sha: str) -> int:
    records = read_jsonl(corpus_path)
    votes = _valid_votes(read_jsonl(ledger_path), stage, sha)
    decided = 0
    for r in records:
        if r.get("phase", PrismaPhase.identified.value) not in _ELIGIBLE[stage]:
            continue
        rv = dict(votes.get(r["id"], {}))
        for alias in r.get("previous_ids", []):  # votes cast before a merge changed the record's id
            for k, v in votes.get(alias, {}).items():
                rv.setdefault(k, v)
        if not _decidable(rv, r, stage):
            continue
        liberal = stage is Stage.title_abstract and not r.get("abstract")
        result = aggregate([rv[k] for k in sorted(rv)], liberal=liberal)
        if stage is Stage.title_abstract:
            r["phase"] = (PrismaPhase.screened_in if result["include"] else PrismaPhase.screened_out).value
        else:
            r["phase"] = (PrismaPhase.included if result["include"] else PrismaPhase.excluded_eligibility).value
        others = [d for d in r.get("decisions", []) if d.get("stage") != stage.value]
        mine = [
            Decision(reviewer=k, stage=stage, include=v["include"], reason=v["reason"],
                     at=date.fromisoformat(v["at"][:10]), model=v["model"], prompt_sha256=sha,
                     confidence=_as_float(v["confidence"]), rationale=v["rationale"]).model_dump(mode="json")
            for k, v in sorted(rv.items())
        ]
        # The panel decision is appended last so PRISMA reporting can read decisions[-1].
        panel = {"reviewer": "panel", "stage": stage.value, "include": result["include"],
                 "reason": result["reason"], "votes": result["votes"], "prompt_sha256": sha}
        r["decisions"] = others + mine + [panel]
        decided += 1
    rewrite_jsonl(corpus_path, records)
    return decided


def _as_float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if math.isclose(pe, 1.0) else (po - pe) / (1 - pe)


def fleiss_kappa(ratings: list[list[bool]]) -> float | None:
    """Fleiss' κ for binary ratings; each inner list holds one item's votes (equal raters)."""

    if not ratings:
        return None
    m = len(ratings[0])
    n = len(ratings)
    p_items, p_yes = [], 0
    for votes in ratings:
        yes = sum(votes)
        p_yes += yes
        p_items.append((yes * (yes - 1) + (m - yes) * (m - yes - 1)) / (m * (m - 1)))
    p_bar = sum(p_items) / n
    p1 = p_yes / (n * m)
    pe = p1**2 + (1 - p1) ** 2
    return None if math.isclose(pe, 1.0) else (p_bar - pe) / (1 - pe)


def agreement_report(stage: Stage, ledger_path: Path | None = None, prompt_path: Path = PROMPT_FILE) -> dict:
    _, _, sha = load_prompt(prompt_path)
    votes = _valid_votes(read_jsonl(ledger_path or _ledger_path(stage)), stage, sha)
    full = {rid: v for rid, v in votes.items() if set(v) == set(PANEL)}
    reviewers = sorted(PANEL)
    matrix = [[full[rid][k]["include"] for k in reviewers] for rid in sorted(full)]
    # In adaptive mode R3 votes on ties and the audit sample only; the unbiased 3-rater
    # estimate uses the audit sample, and R1-R2 agreement uses every record.
    audit_rows = [[full[rid][k]["include"] for k in reviewers] for rid in sorted(full) if in_audit(rid)]
    both = [v for v in votes.values() if set(PRIMARY) <= set(v)]
    pairwise = {
        f"{a}-{b}": cohen_kappa([row[i] for row in matrix], [row[j] for row in matrix])
        for (i, a), (j, b) in combinations(enumerate(reviewers), 2)
    }
    pairwise["R1-R2 (all records)"] = cohen_kappa([v["R1"]["include"] for v in both], [v["R2"]["include"] for v in both])
    split = Counter(sum(row) for row in matrix)
    return {
        "stage": stage.value, "prompt_sha256": sha, "records_fully_voted": len(matrix),
        "records_voted_by_r1_r2": len(both),
        "fleiss_kappa_audit_sample": fleiss_kappa(audit_rows), "audit_sample_size": len(audit_rows),
        "fleiss_kappa": fleiss_kappa(matrix), "cohen_kappa": pairwise,
        "include_votes_distribution": {f"{k}/3": split.get(k, 0) for k in range(4)},
        "include_rate_by_reviewer": {
            k: (sum(row[i] for row in matrix) / len(matrix) if matrix else None)
            for i, k in enumerate(reviewers)
        },
    }
