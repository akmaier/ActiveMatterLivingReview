"""Evidence for the author's conflict resolution (PROTOCOL §6 and §7, amendment 5).

Where the panel split at full text, or the extractors gave three different values, each model is
asked to restate its answer and to quote the passages of the full text that establish it. Every
quote is checked against the text (`verify`), and the claims with their quotes are shown to the
author on the /check/ page, who judges. The models do not decide; they argue with evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import REPO_ROOT
from .extract import field_values, load_prompt as load_extraction_prompt
from .human import FIELD_DEFS, _is_split, _votes
from .llm import PANEL, chat, client_for, parse_json_object
from .schema import PrismaPhase, Stage
from .storage import read_jsonl

PROMPT_FILE = REPO_ROOT / "protocol" / "evidence_prompt.md"
LEDGER = REPO_ROOT / "data" / "conflicts" / "evidence.jsonl"
MAX_TEXT_CHARS = 60_000
MAX_QUOTE_WORDS = 40
_SCREEN, _EXTRACT, _RECORD = "<!-- SCREENING TASK -->", "<!-- EXTRACTION TASK -->", "<!-- RECORD TEMPLATE -->"


def load_prompt(path: Path = PROMPT_FILE) -> tuple[str, str, str, str, str]:
    text = path.read_text(encoding="utf-8")
    system, rest = text.split(_SCREEN, 1)
    screen, rest = rest.split(_EXTRACT, 1)
    extract, record = rest.split(_RECORD, 1)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return system.strip(), screen.strip(), extract.strip(), record.strip(), sha


# ---- quote verification ------------------------------------------------------------------

_DASH = re.compile("[‐‑‒–—−]")


def _norm(s: str) -> str:
    """Lower-case letters and digits only, so PDF-extraction noise (ligatures, odd dashes and
    spaces, line-break hyphenation, punctuation) does not decide whether a quote is found."""

    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"-\s*\n\s*", "", _DASH.sub("-", s))  # hyphenation across line breaks
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _grams(words: list[str], n: int = 5) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def verify(quote: str, text: str, text_grams: set | None = None) -> str:
    """'verbatim' if the quote occurs in the text, 'close' if >= 80 % of its 5-word sequences do,
    'partial' if >= 40 % do (quote stitched or partly paraphrased), 'not_found' otherwise."""

    q, t = _norm(quote), _norm(text)
    if not q:
        return "not_found"
    if q in t:
        return "verbatim"
    qg = _grams(q.split())
    if not qg:
        return "not_found"
    tg = text_grams if text_grams is not None else _grams(t.split())
    share = sum(g in tg for g in qg) / len(qg)
    return "close" if share >= 0.8 else "partial" if share >= 0.4 else "not_found"


def _clean_evidence(items, text: str, tg: set) -> list[dict]:
    out = []
    for e in (items or [])[:4]:
        if not isinstance(e, dict) or not isinstance(e.get("quote"), str):
            continue
        words = e["quote"].split()
        quote = " ".join(words[:MAX_QUOTE_WORDS]) + (" …" if len(words) > MAX_QUOTE_WORDS else "")
        out.append({"criterion": e.get("criterion"), "quote": quote, "check": verify(" ".join(words), text, tg)})
    return out


# ---- tasks -------------------------------------------------------------------------------

def _decision_text(v: dict) -> str:
    if v.get("include") is None:
        return "none recorded"
    return "include" if v["include"] else f"exclude ({v.get('reason') or 'no reason given'})"


def screening_tasks(records: list[dict]) -> list[dict]:
    tasks = []
    for r in records:
        if not _is_split(r):
            continue
        for v in _votes(r, Stage.full_text.value)["reviewers"]:
            tasks.append({"kind": "ft_split", "record": r, "reviewer": v["r"], "field": None,
                          "earlier": {"decision": _decision_text(v), "rationale": v.get("rationale") or "none"}})
    return tasks


def extraction_tasks(records: list[dict], xvotes: dict[str, dict[str, dict]]) -> list[dict]:
    tasks = []
    for r in records:
        e = r.get("extraction") or {}
        if r.get("phase") != PrismaPhase.included.value or not e.get("unresolved"):
            continue
        pending = [f for f in e["unresolved"] if f not in (e.get("author_resolved") or {})]
        for rv, data in xvotes.get(r["id"], {}).items():
            vals = field_values(data)
            fields = [{"field": f, "definition": FIELD_DEFS.get(f, f), "earlier": vals.get(f)} for f in pending]
            if fields:
                tasks.append({"kind": "extraction", "record": r, "reviewer": rv, "fields": fields})
    return tasks


def _render(task: dict, prompt: tuple, text: str) -> tuple[str, str]:
    system, screen, extract, record, _ = prompt
    if task["kind"] == "ft_split":
        body = screen.format(**task["earlier"])
    else:
        body = extract.format(fields="\n".join(
            f"- {f['field']} ({f['definition']}); your earlier value: {json.dumps(f['earlier'])}" for f in task["fields"]))
    r = task["record"]
    user = record.format(title=r.get("title") or "", year=r.get("year") or "unknown",
                         venue=r.get("venue") or "unknown", body=text[:MAX_TEXT_CHARS])
    return system.replace("{task}", body), user


def _done(ledger: Path, sha: str) -> set[tuple]:
    return {(v["kind"], v["record_id"], v["reviewer"]) for v in _rows(ledger)
            if v.get("prompt_sha256") == sha and v.get("error") is None}


def _rows(ledger: Path) -> list[dict]:
    """The main ledger plus per-run siblings (evidence-<name>.jsonl), so parallel runs never
    write to the same file."""

    return [v for f in sorted(ledger.parent.glob(ledger.stem + "*.jsonl")) for v in read_jsonl(f)]


def _ask(task: dict, prompt: tuple, text: str) -> dict:
    sha = prompt[-1]
    r = task["record"]
    row = {"kind": task["kind"], "record_id": r["id"], "reviewer": task["reviewer"], "model": PANEL[task["reviewer"]],
           "prompt_sha256": sha, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "answer": None, "error": None, "elapsed_s": None}
    t0 = time.monotonic()
    try:
        system, user = _render(task, prompt, text)
        resp = chat(client_for(PANEL[task["reviewer"]]), system, user, max_tokens=8192)
        row["raw"] = resp.content
        if task["kind"] == "ft_split":
            ans = parse_json_object(resp.content, "decision")
        else:
            try:
                ans = parse_json_object(resp.content, "fields")
            except ValueError:  # some models drop the "fields" wrapper and key by field name
                ans = {"fields": parse_json_object(resp.content, task["fields"][0]["field"])}
        tg = _grams(_norm(text).split())
        if task["kind"] == "ft_split":
            row["answer"] = {"decision": ans.get("decision"), "reason": ans.get("reason"), "claim": ans.get("claim"),
                             "evidence": _clean_evidence(ans.get("evidence"), text, tg)}
        else:
            want = {f["field"] for f in task["fields"]}
            row["answer"] = {"fields": {f: {"value": v.get("value"), "claim": v.get("claim"),
                                            "evidence": _clean_evidence(v.get("evidence"), text, tg)}
                                        for f, v in (ans.get("fields") or {}).items()
                                        if f in want and isinstance(v, dict)}}
    except Exception as e:  # recorded and retried on the next run
        row["error"] = f"{type(e).__name__}: {e}"[:500]
    row["elapsed_s"] = round(time.monotonic() - t0, 2)
    return row


def run(corpus: Path, text_for: Callable[[dict], str | None], *, kinds=("ft_split", "extraction"),
        reviewers=("R1", "R2", "R3"), limit: int | None = None, workers: int = 6, ledger: Path = LEDGER) -> dict:
    from .human import _extraction_votes

    prompt = load_prompt()
    records = read_jsonl(corpus)
    tasks = []
    if "ft_split" in kinds:
        tasks += screening_tasks(records)
    if "extraction" in kinds:
        tasks += extraction_tasks(records, _extraction_votes())
    done = _done(ledger, prompt[-1])
    tasks = [t for t in tasks if t["reviewer"] in reviewers
             and (t["kind"], t["record"]["id"], t["reviewer"]) not in done]
    texts = {}
    for t in tasks:
        rid = t["record"]["id"]
        if rid not in texts:
            texts[rid] = text_for(t["record"])
    tasks = [t for t in tasks if texts.get(t["record"]["id"])][: limit or None]
    # DeepSeek (R3) is slow: start its requests first so they overlap with the others.
    tasks.sort(key=lambda t: t["reviewer"] != "R3")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    with ThreadPoolExecutor(max_workers=workers) as pool, ledger.open("a", encoding="utf-8") as fh:
        for row in pool.map(lambda t: _ask(t, prompt, texts[t["record"]["id"]]), tasks):
            errors += row["error"] is not None
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
    return {"asked": len(tasks), "errors": errors, "prompt_sha256": prompt[-1]}


def latest(ledger: Path = LEDGER) -> dict[tuple, dict]:
    """(kind, record_id, reviewer) -> latest successful answer under the current prompt."""

    if not PROMPT_FILE.exists():
        return {}
    sha = load_prompt()[-1]
    out = {}
    for v in _rows(ledger):
        if v.get("prompt_sha256") == sha and v.get("answer") is not None:
            out[(v["kind"], v["record_id"], v["reviewer"])] = v
    return out


def recheck(answer: dict, text: str) -> dict:
    """Re-run the quote check on a stored answer (the checker improves; the ledger is not rewritten)."""

    tg = _grams(_norm(text).split())

    def fix(items):
        return [{**e, "check": verify(e["quote"].rstrip(" …"), text, tg)} for e in items or []]

    if "fields" in answer:
        return {"fields": {f: {**v, "evidence": fix(v.get("evidence"))} for f, v in answer["fields"].items()}}
    return {**answer, "evidence": fix(answer.get("evidence"))}
