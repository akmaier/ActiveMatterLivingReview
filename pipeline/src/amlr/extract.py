"""Structured data extraction and risk-of-bias rating for included studies (PROTOCOL §7, §9).

R1 and R3 extract independently with the frozen prompt `protocol/extraction_prompt.md`.
Fields are compared (coded: exact; lists: as sets; counts: within 10 %); only disputed fields
are put to R2, and settled by majority. Fields with three different answers are flagged for the
author. Free-text fields are kept from both extractors, not compared.
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from experteye_scraper.scrum.rrze_client import RRZEClientError, Transport

from .config import REPO_ROOT
from .llm import PANEL, chat, client_for, parse_json_object
from .schema import PrismaPhase
from .storage import locked, read_jsonl, rewrite_jsonl

PROMPT_FILE = REPO_ROOT / "protocol" / "extraction_prompt.md"
LEDGER = REPO_ROOT / "data" / "extraction" / "votes.jsonl"
FINAL = REPO_ROOT / "data" / "extraction" / "extractions.jsonl"
EXTRACTORS = ("R1", "R3")
ARBITER = "R2"
MAX_TEXT_CHARS = 60_000
_SPLIT = "<!-- RECORD TEMPLATE -->"

CODED = ["platform_class", "propulsion", "control_architecture", "agreement", "code_available", "data_available"]
SETS = ["interaction_modality", "phenomena", "theory_compared"]
COUNTS = ["n_agents_min", "n_agents_max", "n_independent_runs"]
SIZES = ["agent_size_mm"]
FREE = ["platform_name", "environment", "observables", "notes"]
ROB = ["D1_replication", "D2_agent_heterogeneity", "D3_finite_size_and_boundaries",
       "D4_measurement_validity", "D5_data_code_availability", "D6_quantitative_theory_comparison"]


def load_prompt(path: Path = PROMPT_FILE) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8")
    system, template = text.split(_SPLIT, 1)
    return system.strip(), template.strip(), hashlib.sha256(text.encode("utf-8")).hexdigest()


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _close(a, b, rel: float) -> bool:
    a, b = _num(a), _num(b)
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= rel * max(abs(a), abs(b), 1.0)


def field_values(d: dict) -> dict:
    """Flatten an extraction into comparable fields (risk-of-bias ratings as rob.<domain>)."""

    out = {f: d.get(f) for f in CODED + SETS + COUNTS + SIZES}
    # The frozen prompt asks for true only when a repository or archive is named, so "not stated"
    # (null) and false both mean "no named repository" and are compared as such.
    for f in ("code_available", "data_available"):
        out[f] = out[f] is True
    rob = d.get("rob") or {}
    for dom in ROB:
        v = rob.get(dom)
        out[f"rob.{dom}"] = (v.get("rating") if isinstance(v, dict) else v)
    return out


def same(field: str, a, b) -> bool:
    if field in SETS:
        return set(a or []) == set(b or [])
    if field in COUNTS:
        return _close(a, b, 0.10)
    if field in SIZES:
        return _close(a, b, 0.25)
    norm = lambda v: v.strip().lower() if isinstance(v, str) else v
    return norm(a) == norm(b)


def disputed(a: dict, b: dict) -> list[str]:
    fa, fb = field_values(a), field_values(b)
    return [f for f in fa if not same(f, fa[f], fb[f])]


def reconcile(a: dict, b: dict, c: dict | None) -> tuple[dict, list[str]]:
    """Final values: agreed fields from a; disputed fields by majority with arbiter c."""

    fa, fb = field_values(a), field_values(b)
    fc = field_values(c) if c else {}
    final, unresolved = dict(fa), []
    for f in disputed(a, b):
        if f in SETS and c is not None:
            # Multi-label fields: label-wise majority (a label is kept if >= 2 of 3 extractors chose it).
            sets = [set(x.get(f) or []) for x in (fa, fb, fc)]
            final[f] = sorted({lab for lab in set().union(*sets) if sum(lab in s for s in sets) >= 2})
        elif f.startswith("rob.") and c is not None and len({fa[f], fb[f], fc.get(f)}) == 3 \
                and {fa[f], fb[f], fc.get(f)} <= {"low", "some_concerns", "high"}:
            final[f] = "some_concerns"  # PROTOCOL §9: all three ratings differ -> "some concerns"
        elif c is not None and same(f, fc.get(f), fa[f]):
            final[f] = fa[f]
        elif c is not None and same(f, fc.get(f), fb[f]):
            final[f] = fb[f]
        else:
            final[f] = None
            unresolved.append(f)
    for f in FREE:
        final[f] = a.get(f) if a.get(f) not in (None, "", []) else b.get(f)
        final[f"{f}_alt"] = b.get(f)
    final["rob_why"] = {k: ((a.get("rob") or {}).get(k) or {}).get("why") if isinstance((a.get("rob") or {}).get(k), dict) else None
                        for k in ROB}
    return final, unresolved


def _vote(reviewer: str, system: str, user: str, sha: str, record_id: str, transport: Transport | None) -> dict:
    row = {"record_id": record_id, "reviewer": reviewer, "model": PANEL[reviewer], "prompt_sha256": sha,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data": None, "raw": None,
           "error": None, "elapsed_s": None}
    t0 = time.monotonic()
    try:
        resp = chat(client_for(PANEL[reviewer], transport=transport), system, user, max_tokens=8192)
        row["raw"] = resp.content
        row["data"] = parse_json_object(resp.content, "platform_class")
    except Exception as e:  # recorded and retried on the next run; one failure must not end the batch
        row["error"] = f"{type(e).__name__}: {e}"[:500]
    row["elapsed_s"] = round(time.monotonic() - t0, 2)
    return row


def _latest(ledger: Path, sha: str) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for v in read_jsonl(ledger):
        if v["prompt_sha256"] == sha and v["data"] is not None:
            out.setdefault(v["record_id"], {})[v["reviewer"]] = v["data"]
    return out


def run(corpus: Path, text_for: Callable[[dict], str | None], *, limit: int | None = None, workers: int = 4,
        transport: Transport | None = None, ledger: Path = LEDGER, final_path: Path = FINAL) -> dict:
    system, template, sha = load_prompt()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    records = [r for r in read_jsonl(corpus) if r.get("phase") == PrismaPhase.included.value]
    records = records[: limit or None]
    prompts = {}
    for r in records:
        text = text_for(r)
        if text:
            prompts[r["id"]] = template.format(title=r.get("title") or "", year=r.get("year") or "unknown",
                                               venue=r.get("venue") or "unknown", body=text[:MAX_TEXT_CHARS])
    done = _latest(ledger, sha)

    def execute(tasks):
        with ThreadPoolExecutor(max_workers=workers) as pool, ledger.open("a", encoding="utf-8") as fh:
            for row in pool.map(lambda t: _vote(t[1], system, prompts[t[0]], sha, t[0], transport), tasks):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    execute([(rid, rv) for rid in prompts for rv in EXTRACTORS if rv not in done.get(rid, {})])
    done = _latest(ledger, sha)
    execute([(rid, ARBITER) for rid, v in done.items() if rid in prompts and set(EXTRACTORS) <= set(v)
             and ARBITER not in v and disputed(v[EXTRACTORS[0]], v[EXTRACTORS[1]])])
    done = _latest(ledger, sha)

    finals, n_unresolved = [], 0
    for rid in prompts:
        v = done.get(rid, {})
        if not set(EXTRACTORS) <= set(v):
            continue
        d = disputed(v[EXTRACTORS[0]], v[EXTRACTORS[1]])
        if d and ARBITER not in v:
            continue
        final, unresolved = reconcile(v[EXTRACTORS[0]], v[EXTRACTORS[1]], v.get(ARBITER))
        n_unresolved += bool(unresolved)
        finals.append({"record_id": rid, "prompt_sha256": sha, "disputed": d, "unresolved": unresolved, **final})
    with final_path.open("w", encoding="utf-8") as fh:
        for row in finals:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _apply(corpus, {f["record_id"]: f for f in finals})
    return {"included": len(records), "with_text": len(prompts), "extracted": len(finals),
            "with_unresolved_fields": n_unresolved, "prompt_sha256": sha}


def _apply(corpus: Path, finals: dict[str, dict]) -> None:
    with locked(corpus):
        records = read_jsonl(corpus)
        for r in records:
            if r["id"] in finals:
                r["extraction"] = {k: v for k, v in finals[r["id"]].items() if k != "record_id"}
        rewrite_jsonl(corpus, records)
