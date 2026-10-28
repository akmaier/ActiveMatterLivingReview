"""Living update: windowed search, incremental merge into the corpus, panel work on new records only.

The corpus (data/corpus.jsonl) is gitignored, so its state travels in the repository as
data/state/corpus.jsonl.gz: every record with its phase, decisions and extraction; abstracts are
dropped for excluded records (they are no longer needed and are the bulk of the file).

An update never rebuilds the corpus from scratch. Previous records keep their id, phase and
decisions; a newly retrieved row that matches one (same DOI, arXiv id, PMID, source id or title)
only adds its source identifiers. Unmatched rows become new records in phase `identified`,
tagged with `identified_in_update`. The screening ledgers then skip everything already decided,
so the panel only votes on new records.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import search
from .config import REPO_ROOT
from .corpus import CORPUS, MANIFEST, SUPPLEMENTARY
from .dedup import cluster, fold
from .schema import PrismaPhase as P
from .storage import locked, read_jsonl, rewrite_jsonl

STATE_DIR = REPO_ROOT / "data" / "state"
STATE_CORPUS = STATE_DIR / "corpus.jsonl.gz"
STATE_META = STATE_DIR / "state.json"
UPDATES_RAW = REPO_ROOT / "data" / "raw" / "updates"
SNAPSHOTS = REPO_ROOT / "data" / "snapshots"
CHANGELOG = REPO_ROOT / "_data" / "changelog.yml"
FIRST_SEARCH = "2026-10-11"  # PROTOCOL.md §4: first searches, database inception to this date
# Searches overlap the previous window; duplicates are removed against the corpus.
OVERLAP_DAYS = 14
# Abstracts kept in the state file: records that may still be screened or are shown on the site.
_KEEP_ABSTRACT = {P.identified.value, P.screened_in.value, P.fulltext_sought.value,
                  P.fulltext_not_retrieved.value, P.assessed.value, P.included.value}
_RANK = {"included": 6, "excluded_eligibility": 6, "fulltext_not_retrieved": 5, "assessed": 4,
         "fulltext_sought": 3, "screened_in": 3, "screened_out": 2, "identified": 1, "duplicate": 0}


# ---------------------------------------------------------------- state file

def _meta() -> dict:
    return json.loads(STATE_META.read_text()) if STATE_META.exists() else {"last_search": FIRST_SEARCH}


def save_state(corpus: Path = CORPUS, last_search: str | None = None) -> dict:
    rows = read_jsonl(corpus)
    slim = [r if r.get("phase") in _KEEP_ABSTRACT else {**r, "abstract": None} for r in rows]
    payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in slim).encode()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_CORPUS.open("wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(payload)
    meta = _meta() | {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "records": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}
    if last_search:
        meta["last_search"] = last_search
    STATE_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def restore_state(corpus: Path = CORPUS, force: bool = False) -> str:
    """Unpack the committed state into data/corpus.jsonl (kept if one exists, unless `force`)."""

    if corpus.exists() and not force:
        return f"kept existing {corpus.name}"
    if not STATE_CORPUS.exists():
        raise FileNotFoundError(f"{STATE_CORPUS} missing; run `amlr state-save` on the machine with the corpus")
    with gzip.open(STATE_CORPUS, "rb") as gz:
        corpus.write_bytes(gz.read())
    return f"restored {_meta().get('records')} records from {STATE_CORPUS.name}"


# ---------------------------------------------------------------- windowed search

def window(since: str | None = None) -> tuple[str, str]:
    start = date.fromisoformat(since) if since else date.fromisoformat(_meta()["last_search"]) - timedelta(OVERLAP_DAYS)
    return start.isoformat(), date.today().isoformat()


def fetch_window(sources: list[str], since: str, out_dir: Path) -> tuple[dict, list[dict]]:
    """Run each source restricted to `since`..today; a failing source is reported, not fatal."""

    from .fetch import FETCHERS, fetch

    search.WINDOW = since
    results, rows = {}, []
    try:
        for src in sources:
            if src not in FETCHERS:
                results[src] = {"error": "unknown source"}
                continue
            try:
                res = fetch(src, out_dir)
            except Exception as e:  # one outage (or a missing token) must not block the others
                results[src] = {"error": f"{type(e).__name__}: {e}"[:300]}
                continue
            results[src] = res
            if res.get("paused"):
                continue  # incomplete OpenAlex pull: rerun the update after the credit reset
            if f := res.get("records_file"):
                rows.extend(read_jsonl(Path(f)))
    finally:
        search.WINDOW = None
    return results, rows


# ---------------------------------------------------------------- incremental merge

def _attach(target: dict, news: list[dict]) -> None:
    ids = dict(target.get("source_ids") or {})
    id_list = {tuple(x) for x in target.get("source_id_list") or []}
    dois = set(target.get("all_dois") or [])
    prov = dict(target.get("provenance") or {})
    for r in news:
        for s, sid in (r.get("source_ids") or {}).items():
            ids.setdefault(s, sid)
            id_list.add((s, str(sid)))
        if r.get("doi"):
            dois.add(str(r["doi"]).lower())
        prov.update(r.get("provenance") or {})
    target.update(source_ids=ids, source_id_list=sorted(id_list), all_dois=sorted(dois),
                  provenance=prov, sources=sorted(ids))


def merge_new(rows: list[dict], stamp: str, corpus: Path = CORPUS) -> dict:
    """Add new rows to the corpus without touching the state of previous records."""

    with locked(corpus):
        old = read_jsonl(corpus)
        old_ids = {id(r) for r in old}
        known = {r["id"] for r in old}
        added, matched, within = [], 0, 0
        for group in cluster(old + rows):
            news = [r for r in group if id(r) not in old_ids]
            if not news:
                continue
            olds = [r for r in group if id(r) in old_ids]
            if olds:
                _attach(max(olds, key=lambda r: _RANK.get(r.get("phase", "identified"), 0)), news)
                matched += len(news)
                continue
            rec = fold(news)
            if rec["id"] in known:  # a stable id can coincide with an unlinked previous record
                rec["id"] = f"{rec['id']}#u{stamp}"
            known.add(rec["id"])
            rec.update(phase=P.identified.value, identified_in_update=stamp)
            added.append(rec)
            within += len(news) - 1
        rewrite_jsonl(corpus, old + added)
    return {"rows": len(rows), "already_in_review": matched, "duplicates_within_update": within,
            "new_records": len(added)}


def update_manifest(stamp: str, since: str, fetched: dict, merge: dict, rows: list[dict]) -> None:
    """Cumulative identification counts: identified − duplicates still equals the corpus size."""

    m = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {
        "per_source": {}, "identified_db": 0, "identified_other": 0, "duplicates_removed": 0}
    per_source: dict[str, int] = {}
    for r in rows:
        src = next(iter(r.get("provenance") or {"?": None}))
        per_source[src] = per_source.get(src, 0) + 1
    db = sum(n for s, n in per_source.items() if s not in SUPPLEMENTARY)
    other = sum(n for s, n in per_source.items() if s in SUPPLEMENTARY)
    m["identified_db"] += db
    m["identified_other"] += other
    m["duplicates_removed"] += merge["already_in_review"] + merge["duplicates_within_update"]
    for s, n in per_source.items():
        entry = m["per_source"].setdefault(s, {"records": 0})
        entry["records"] = entry.get("records", 0) + n
    m.setdefault("updates", []).append({
        "date": stamp, "window_from": since, "per_source": per_source,
        "errors": {s: v["error"] for s, v in fetched.items() if "error" in v},
        "paused": {s: v["paused"] for s, v in fetched.items() if v.get("paused")},
        "identified_db": db, "identified_other": other, **merge})
    m["after_dedup"] = m["identified_db"] + m["identified_other"] - m["duplicates_removed"]
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- report

def update_counts(stamp: str, corpus: Path = CORPUS) -> dict:
    new = [r for r in read_jsonl(corpus) if r.get("identified_in_update") == stamp]
    phases: dict[str, int] = {}
    for r in new:
        phases[r.get("phase", "identified")] = phases.get(r.get("phase", "identified"), 0) + 1
    return {"new_records": len(new), "by_phase": dict(sorted(phases.items())),
            "included": sorted((r["id"], r.get("title") or "") for r in new if r.get("phase") == P.included.value),
            "awaiting_full_text": sorted((r["id"], r.get("doi") or "") for r in new
                                         if r.get("phase") in (P.screened_in.value, P.fulltext_sought.value))}


def _changelog(stamp: str, since: str, merge: dict, counts: dict, total_included: int) -> None:
    import yaml

    entry = {
        "date": stamp,
        "title": "Monthly living update",
        "summary": (f"Searches re-run for {since} to {stamp}: {merge['rows']} records retrieved, "
                    f"{merge['already_in_review']} already in the review, {merge['new_records']} new. "
                    f"{counts['by_phase'].get('screened_out', 0)} excluded at title/abstract, "
                    f"{len(counts['awaiting_full_text'])} awaiting full text, "
                    f"{len(counts['included'])} included. The review now includes {total_included} studies."),
        "added": f"{len(counts['included'])} included studies" if counts["included"] else None,
    }
    entry = {k: v for k, v in entry.items() if v is not None}
    text = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Append-only; newest first.\n"
    head, _, rest = text.partition("\n- date:")
    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, width=100)
    CHANGELOG.write_text(head + "\n" + block + ("- date:" + rest if rest else ""), encoding="utf-8")


def write_report(stamp: str, since: str, fetched: dict, merge: dict, counts: dict, steps: dict) -> Path:
    snap = SNAPSHOTS / stamp
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "update_counts.json").write_text(json.dumps(
        {"date": stamp, "window_from": since, "fetch": fetched, "merge": merge, "steps": steps, **counts},
        indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    lines = [f"## Living update {stamp}", "", f"Search window: {since} to {stamp}.", "",
             "| Source | Records | Note |", "|---|---:|---|"]
    for s, v in fetched.items():
        lines.append(f"| {s} | {v.get('records', v.get('records_so_far', '–'))} | "
                     f"{v.get('error') or v.get('paused') or ''} |")
    lines += ["", f"- Retrieved: {merge['rows']}; already in the review: {merge['already_in_review']}; "
              f"duplicates within the update: {merge['duplicates_within_update']}; new records: {merge['new_records']}",
              f"- New records by phase: {counts['by_phase']}", ""]
    if counts["included"]:
        lines += ["### Newly included", ""] + [f"- `{i}` {t}" for i, t in counts["included"]] + [""]
    if counts["awaiting_full_text"]:
        lines += ["### Awaiting full text (retrieve locally: `amlr fulltext --retry`, then `amlr fulltext-browser`)", ""]
        lines += [f"- `{i}` {d}" for i, d in counts["awaiting_full_text"]] + [""]
    lines += ["### Steps", ""] + [f"- {k}: {v}" for k, v in steps.items()] + [
        "", "The manuscript is not regenerated by this workflow; counts in paper/ are updated in a drafting round."]
    out = snap / "UPDATE.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- the whole update

DEFAULT_SOURCES = ["openalex", "arxiv", "pubmed", "hal", "europepmc_biorxiv", "crossref", "ads", "submissions"]


def run(sources: list[str] | None = None, since: str | None = None, *, screen: bool = True,
        fulltext: bool = True, extract: bool = True, workers: int = 6) -> dict:
    from .fulltext.dispatch import run as fulltext_run
    from .fulltext.dispatch import text_for
    from .schema import Stage
    from .screen_llm import run_panel

    stamp = date.today().isoformat()
    steps: dict = {"restore": restore_state()}
    since, _ = window(since)
    sources = list(sources or DEFAULT_SOURCES)
    if "ads" in sources:
        try:
            search.ads_token()
        except RuntimeError:
            sources.remove("ads")
            steps["ads"] = "skipped: no ADS_TOKEN"
    fetched, rows = fetch_window(sources, since, UPDATES_RAW / stamp)
    merge = merge_new(rows, stamp)
    update_manifest(stamp, since, fetched, merge, rows)
    if screen:
        steps["title_abstract"] = run_panel(Stage.title_abstract, CORPUS, workers=workers)
    if fulltext:
        steps["fulltext"] = fulltext_run(CORPUS, retry=True)
    if screen:
        steps["full_text"] = run_panel(Stage.full_text, CORPUS, workers=workers, full_text_for=text_for)
    if extract:
        from .extract import run as extract_run
        steps["extract"] = extract_run(CORPUS, text_for, workers=4)
    counts = update_counts(stamp)
    total = sum(1 for r in read_jsonl(CORPUS) if r.get("phase") == P.included.value)
    complete = not any("error" in v or v.get("paused") for v in fetched.values())
    # The window only advances when every source answered, so a failed source is re-searched next time.
    meta = save_state(last_search=stamp if complete else None)
    _changelog(stamp, since, merge, counts, total)
    report = write_report(stamp, since, fetched, merge, counts, steps)
    return {"date": stamp, "window_from": since, "merge": merge, "new_by_phase": counts["by_phase"],
            "included_total": total, "window_advanced": complete, "state": meta, "report": str(report)}
