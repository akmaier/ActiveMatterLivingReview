"""Human-assisted retrieval: a click-through list for the author's own browser, and import of the
PDFs the author saved (e.g. to ~/Downloads), matched to records by DOI, Elsevier PII, or title.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from ..config import REPO_ROOT
from ..schema import PrismaPhase
from ..storage import read_jsonl
from .browser import plan
from .dispatch import LEDGER, PDF_DIR, apply, extract_text, slug

LIST_DIR = REPO_ROOT / "data" / "fulltext"
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
_PII = re.compile(r"\bS\d{4}-?\d{3}[\dX]\(?\d{2}\)?\d{5}-?[\dX]\b|\bS\d{15}[\dX]\b", re.I)


def missing(corpus: Path, include_ieee: bool = False) -> list[dict]:
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    out = []
    for r in read_jsonl(corpus):
        if r.get("phase") != PrismaPhase.fulltext_sought.value or latest.get(r["id"], {}).get("status") == "retrieved":
            continue
        p = plan(r)
        if p and p[0] == "ieeexplore.ieee.org" and not include_ieee:
            continue
        out.append(r)
    return out


def write_list(corpus: Path, include_ieee: bool = False) -> Path:
    rows = missing(corpus, include_ieee)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = LIST_DIR / f"manual-{stamp}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    items = []
    for i, r in enumerate(sorted(rows, key=lambda r: (r.get("doi") or "~").split("/")[0]), 1):
        title = html.escape(r.get("title") or r["id"])
        if r.get("doi"):
            link = f"https://doi.org/{html.escape(r['doi'])}"
            label = html.escape(r["doi"])
        else:
            link = "https://scholar.google.com/scholar?q=" + urllib.parse.quote(f'"{r.get("title", "")}"')
            label = "search by title"
        items.append(f'<li><a href="{link}" target="_blank">{title}</a> <small>({label}, {r.get("year") or "n.d."})</small></li>')
    out.write_text(
        "<!doctype html><meta charset='utf-8'><title>Full texts to save</title>"
        "<style>body{font:15px/1.5 -apple-system,Helvetica,sans-serif;max-width:900px;margin:2em auto;padding:0 1em}"
        "li{margin:.4em 0}small{color:#666}</style>"
        f"<h1>{len(rows)} full texts to save</h1><p>Open each link, use the publisher's own "
        "<em>Download PDF</em>, and save to ~/Downloads. Then run <code>amlr fulltext-import</code>.</p>"
        f"<ol>{''.join(items)}</ol>", encoding="utf-8")
    return out


def _first_pages_text(pdf: Path, pages: int = 2) -> tuple[str, int, str]:
    import pymupdf

    doc = pymupdf.open(pdf)
    meta = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
    text = " ".join(doc[i].get_text() for i in range(min(pages, doc.page_count)))
    return text, doc.page_count, meta


_WORD = re.compile(r"[a-z]{4,}")


def title_region(page_text: str, n_words: int = 35) -> str:
    """Opening words of page 1, cut before IOP's 'To cite this article' block, which is followed by
    'You may also like' and the titles of other papers."""

    head = re.split(r"To cite this article", page_text, maxsplit=1)[0]
    return " ".join(head.split()[:n_words])


def title_score(title: str, page_text: str) -> float:
    """Share of the record's title words found in the title region of page 1."""

    words = set(_WORD.findall((title or "").lower()))
    region = set(_WORD.findall(title_region(page_text).lower()))
    return len(words & region) / len(words) if len(words) >= 3 else 0.0


def best_title_match(page_text: str, targets: list[dict], min_score: float = 0.9) -> dict | None:
    """Best-scoring record whose title appears in the title region; ties are treated as no match."""

    scored = sorted(((title_score(r.get("title") or "", page_text), r) for r in targets), key=lambda x: -x[0])
    if not scored or scored[0][0] < min_score:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None  # ambiguous
    return scored[0][1]


def _norm_pii(s: str) -> str:
    return re.sub(r"[^0-9X]", "", s.upper())


def import_dir(corpus: Path, src: Path, since: datetime | None = None) -> dict:
    """Match PDFs in `src` (newer than `since`) to missing records; copy matches into docs/."""

    targets = missing(corpus, include_ieee=True)
    by_doi = {(r.get("doi") or "").lower(): r for r in targets if r.get("doi")}
    by_pii = {}
    for r in targets:
        for u in [r.get("doi") or ""] + list((r.get("source_ids") or {}).values()):
            m = _PII.search(str(u))
            if m:
                by_pii[_norm_pii(m.group(0))] = r
    matched, unmatched, too_short = [], [], []
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    rows = []
    for pdf in sorted(src.glob("*.pdf")):
        if since and datetime.fromtimestamp(pdf.stat().st_mtime, timezone.utc) < since:
            continue
        try:
            text, pages, meta = _first_pages_text(pdf)
        except Exception:
            continue
        hay = f"{meta} {text}"
        rec = next((by_doi[d.lower().rstrip(".,;)")] for d in _DOI.findall(hay) if d.lower().rstrip(".,;)") in by_doi), None)
        if rec is None:
            rec = next((by_pii[_norm_pii(p)] for p in _PII.findall(hay) + [pdf.stem] if _norm_pii(p) in by_pii), None)
        if rec is None:
            rec = best_title_match(text, targets)
        if rec is None:
            unmatched.append(pdf.name)
            continue
        if pages <= 1:
            too_short.append(pdf.name)
            continue
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        dest = PDF_DIR / f"{slug(rec)}.pdf"
        shutil.copy2(pdf, dest)
        data = dest.read_bytes()
        txt = extract_text(dest, rec)
        prior = latest.get(rec["id"], {})
        rows.append({"record_id": rec["id"], "doi": rec.get("doi"), "status": "retrieved", "tier": 3,
                     "route": "manual:author_browser", "tried": sorted(set(prior.get("tried", [])) | {"manual"}),
                     "pdf": str(dest.relative_to(REPO_ROOT)), "bytes": len(data),
                     "sha256": hashlib.sha256(data).hexdigest(),
                     "text": str(txt.relative_to(REPO_ROOT)) if txt else None, "source_file": pdf.name,
                     "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        matched.append((pdf.name, rec["id"]))
        targets = [t for t in targets if t["id"] != rec["id"]]
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if rows:
        apply(corpus)
    return {"imported": len(matched), "matches": matched, "unmatched_pdfs": unmatched,
            "rejected_one_page": too_short}


def import_page_text(corpus: Path, files: dict[str, Path], source: str) -> int:
    """Article text read from the publisher's HTML page in the author's browser (no PDF offered).
    `files` maps record id → text file; files are moved into data/fulltext_text/."""

    from .dispatch import TEXT_DIR

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for rid, path in files.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if len(text) < 5000:
            continue
        dest = TEXT_DIR / f"{slug({'id': rid})}.txt"
        if path.resolve() != dest.resolve():
            shutil.move(str(path), dest)
        rows.append({"record_id": rid, "status": "retrieved", "tier": 3, "route": "manual:page_text",
                     "format": "html_text", "pdf": str(dest.relative_to(REPO_ROOT)), "text": str(dest.relative_to(REPO_ROOT)),
                     "bytes": len(text.encode()), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "tried": ["manual"], "source": source, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if rows:
        apply(corpus)
    return len(rows)


def organize_downloads(corpus: Path, src: Path, since: datetime, dry_run: bool = True) -> dict:
    """Sort the author's downloaded PDFs: move new matches into docs/, send duplicates to the Trash.

    Only PDFs matching a screened-in record (page-1 DOI, Elsevier PII, or title region) are touched;
    anything else stays where it is. Duplicates (a second copy of a record in this batch, or a copy of a
    record already retrieved) go to ~/.Trash, so nothing is permanently deleted.
    """

    from .dispatch import TEXT_DIR

    records = [r for r in read_jsonl(corpus)
               if r.get("phase") not in (None, PrismaPhase.identified.value, PrismaPhase.screened_out.value)]
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    retrieved = {rid for rid, a in latest.items() if a.get("status") == "retrieved"}
    by_doi = {(r.get("doi") or "").lower(): r for r in records if r.get("doi")}
    by_pii = {}
    for r in records:
        m = _PII.search(str(r.get("doi") or ""))
        if m:
            by_pii[_norm_pii(m.group(0))] = r
    chosen: dict[str, Path] = {}
    plan_rows = []
    for pdf in sorted(src.glob("*.pdf"), key=lambda p: p.stat().st_mtime):
        if datetime.fromtimestamp(pdf.stat().st_mtime, timezone.utc) < since:
            continue
        try:
            import pymupdf

            doc = pymupdf.open(pdf)
            page1, pages = doc[0].get_text(), doc.page_count
            meta = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
        except Exception:
            plan_rows.append(("leave_unreadable", pdf, None))
            continue
        hay = f"{meta} {page1}"
        rec = next((by_doi[d.lower().rstrip(".,;)")] for d in _DOI.findall(hay) if d.lower().rstrip(".,;)") in by_doi), None)
        if rec is None:
            rec = next((by_pii[_norm_pii(p)] for p in _PII.findall(hay) + [pdf.stem] if _norm_pii(p) in by_pii), None)
        if rec is None:
            rec = best_title_match(page1, records)
        if rec is None:
            plan_rows.append(("leave_unmatched", pdf, None))
        elif rec["id"] in retrieved or rec["id"] in chosen:
            plan_rows.append(("trash_duplicate", pdf, rec))
        elif pages <= 1:
            plan_rows.append(("leave_one_page", pdf, rec))
        else:
            plan_rows.append(("move", pdf, rec))
            chosen[rec["id"]] = pdf
    summary = {k: sum(1 for a, _, _ in plan_rows if a == k) for k in
               ("move", "trash_duplicate", "leave_unmatched", "leave_one_page", "leave_unreadable")}
    if dry_run:
        return summary | {"plan": [(a, p.name, r["id"] if r else None) for a, p, r in plan_rows]}
    trash = Path.home() / ".Trash"
    rows = []
    for action, pdf, rec in plan_rows:
        if action == "move":
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            dest = PDF_DIR / f"{slug(rec)}.pdf"
            shutil.move(str(pdf), dest)
            data = dest.read_bytes()
            txt = extract_text(dest, rec)
            prior = latest.get(rec["id"], {})
            rows.append({"record_id": rec["id"], "doi": rec.get("doi"), "status": "retrieved", "tier": 3,
                         "route": "manual:author_browser", "tried": sorted(set(prior.get("tried", [])) | {"manual"}),
                         "pdf": str(dest.relative_to(REPO_ROOT)), "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest(),
                         "text": str(txt.relative_to(REPO_ROOT)) if txt else None, "source_file": pdf.name,
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        elif action == "trash_duplicate":
            target = trash / pdf.name
            i = 1
            while target.exists():
                target = trash / f"{pdf.stem} ({i}){pdf.suffix}"
                i += 1
            shutil.move(str(pdf), target)
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if rows:
        apply(corpus)
    return summary


def import_assigned(corpus: Path, assigned: dict[str, Path], note: str) -> int:
    """Move PDFs the matcher could not place, assigned to records by hand after inspection."""

    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    recs = {r["id"]: r for r in read_jsonl(corpus)}
    rows = []
    for rid, pdf in assigned.items():
        if not pdf.exists() or rid not in recs:
            continue
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        dest = PDF_DIR / f"{slug(recs[rid])}.pdf"
        shutil.move(str(pdf), dest)
        data = dest.read_bytes()
        txt = extract_text(dest, recs[rid])
        rows.append({"record_id": rid, "doi": recs[rid].get("doi"), "status": "retrieved", "tier": 3,
                     "route": "manual:author_browser", "tried": sorted(set(latest.get(rid, {}).get("tried", [])) | {"manual"}),
                     "pdf": str(dest.relative_to(REPO_ROOT)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                     "text": str(txt.relative_to(REPO_ROOT)) if txt else None, "source_file": pdf.name,
                     "assignment": note, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    if rows:
        apply(corpus)
    return len(rows)
