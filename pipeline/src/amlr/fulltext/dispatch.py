"""Full-text acquisition for records that passed title/abstract screening.

Tier 1  publisher TDM APIs (Elsevier, Wiley) and publisher PDF endpoints reachable with FAU
        institutional IP access (Springer, APS, PLOS, DOI landing page `citation_pdf_url`).
Tier 2  open access: Unpaywall best location, then the arXiv preprint.
Tier 3  Claude in Chrome (manual, per-batch user approval): records left `not_retrieved`.

Every request identifies itself honestly (no browser User-Agent spoofing): a publisher that
refuses scripted access is left to tier 3. PDFs go to docs/ (gitignored), extracted text to
data/fulltext_text/ (gitignored); outcomes are appended to data/fulltext/acquisition.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import REPO_ROOT, load_tdm_config
from ..schema import PrismaPhase
from ..search import MAILTO
from ..storage import locked, read_jsonl, rewrite_jsonl

PDF_DIR = REPO_ROOT / "docs"
TEXT_DIR = REPO_ROOT / "data" / "fulltext_text"
LEDGER = REPO_ROOT / "data" / "fulltext" / "acquisition.jsonl"
MIN_PDF_BYTES = 10_000
UA = f"amlr/0.0.1 (+https://github.com/akmaier/ActiveMatterLivingReview; mailto:{MAILTO})"

_last: dict[str, float] = {}


def _polite(host: str, interval: float) -> None:
    wait = _last.get(host, 0) + interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.monotonic()


def _get(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0, b"", ""


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-" and len(data) >= MIN_PDF_BYTES


def slug(record: dict) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", record["id"])[:150]


# ---------------------------------------------------------------- routes (bytes or None)

def r_elsevier(doi: str, cfg) -> bytes | None:
    if not doi.startswith("10.1016/") or not cfg.elsevier_api_key:
        return None
    _polite("api.elsevier.com", 0.3)
    h = {"X-ELS-APIKey": cfg.elsevier_api_key, "Accept": "application/pdf"}
    if cfg.elsevier_insttoken:
        h["X-ELS-Insttoken"] = cfg.elsevier_insttoken
    _, data, _ = _get(f"https://api.elsevier.com/content/article/doi/{doi}", h)
    return data if is_pdf(data) else None


def r_wiley(doi: str, cfg) -> bytes | None:
    if not doi.startswith(("10.1002/", "10.1111/")) or not cfg.wiley_tdm_token:
        return None
    _polite("api.wiley.com", 3.5)  # Wiley TDM is strictly rate-limited
    _, data, _ = _get(f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{urllib.parse.quote(doi, safe='')}",
                      {"Wiley-TDM-Client-Token": cfg.wiley_tdm_token})
    return data if is_pdf(data) else None


def r_springer(doi: str, cfg) -> bytes | None:
    if not doi.startswith(("10.1007/", "10.1038/", "10.1186/", "10.1140/")):
        return None
    _polite("link.springer.com", 0.5)
    _, data, _ = _get(f"https://link.springer.com/content/pdf/{doi}.pdf", {"Accept": "application/pdf"})
    return data if is_pdf(data) else None


_APS_JOURNAL = {"physrevlett": "prl", "physreve": "pre", "physrevx": "prx", "physrevresearch": "prresearch",
                "revmodphys": "rmp", "physrevapplied": "prapplied", "physrevfluids": "prfluids",
                "physrevmaterials": "prmaterials", "physreva": "pra", "physrevb": "prb"}


def r_aps(doi: str, cfg) -> bytes | None:
    if not doi.startswith("10.1103/"):
        return None
    m = re.match(r"10\.1103/(physrev[a-z]*|revmodphys)\.", doi)
    journal = _APS_JOURNAL.get(m.group(1)) if m else None
    if not journal:
        return None  # new-style APS DOIs carry no journal code: handled by r_landing
    _polite("journals.aps.org", 2.0)
    _, data, _ = _get(f"https://journals.aps.org/{journal}/pdf/{doi}", {"Accept": "application/pdf"})
    return data if is_pdf(data) else None


_META = re.compile(rb'citation_pdf_url["\']\s+content=["\']([^"\']+)|content=["\']([^"\']+)["\']\s+name=["\']citation_pdf_url')


def r_landing(doi: str, cfg) -> bytes | None:
    """DOI landing page → citation_pdf_url, with institutional IP access and an honest UA."""

    _polite("doi.org", 0.5)
    _, body, _ = _get(f"https://doi.org/{doi}", {"Accept": "text/html,application/pdf"}, timeout=30)
    if is_pdf(body):
        return body
    m = _META.search(body)
    if not m:
        return None
    url = (m.group(1) or m.group(2)).decode(errors="ignore")
    _polite(urllib.parse.urlparse(url).netloc, 1.0)
    _, data, _ = _get(url, {"Accept": "application/pdf"})
    return data if is_pdf(data) else None


def r_unpaywall(doi: str, cfg) -> bytes | None:
    _polite("api.unpaywall.org", 0.2)
    code, data, _ = _get(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={MAILTO}", timeout=30)
    if code != 200:
        return None
    try:
        meta = json.loads(data)
    except json.JSONDecodeError:
        return None
    urls = [loc.get("url_for_pdf") for loc in [meta.get("best_oa_location") or {}] + (meta.get("oa_locations") or [])]
    for url in dict.fromkeys(u for u in urls if u):
        _polite(urllib.parse.urlparse(url).netloc, 1.0)
        _, pdf, _ = _get(url, {"Accept": "application/pdf"})
        if is_pdf(pdf):
            return pdf
    return None


def r_arxiv(arxiv_id: str, cfg) -> bytes | None:
    _polite("export.arxiv.org", 3.0)  # arXiv asks automated clients to use export.arxiv.org at ≤ 1 req / 3 s
    _, data, _ = _get(f"https://export.arxiv.org/pdf/{arxiv_id}", {"Accept": "application/pdf"})
    return data if is_pdf(data) else None


DOI_ROUTES: list[tuple[str, int, Callable]] = [
    ("elsevier_tdm", 1, r_elsevier), ("wiley_tdm", 1, r_wiley), ("springer", 1, r_springer),
    ("aps", 1, r_aps), ("landing_page", 1, r_landing), ("unpaywall", 2, r_unpaywall),
]


def acquire(record: dict, cfg) -> dict:
    doi = (record.get("doi") or "").lower()
    tried = []
    data, route, tier = None, None, None
    if doi and not doi.startswith("10.48550/"):
        for name, t, fn in DOI_ROUTES:
            tried.append(name)
            data = fn(doi, cfg)
            if data:
                route, tier = name, t
                break
    if not data and record.get("arxiv_id"):
        tried.append("arxiv")
        data = r_arxiv(record["arxiv_id"], cfg)
        route, tier = ("arxiv", 2) if data else (None, None)
    row = {"record_id": record["id"], "doi": doi or None, "tried": tried,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not data:
        return row | {"status": "not_retrieved", "route": None, "tier": None}
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_DIR / f"{slug(record)}.pdf"
    pdf_path.write_bytes(data)
    row |= {"status": "retrieved", "route": route, "tier": tier, "pdf": str(pdf_path.relative_to(REPO_ROOT)),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    text_path = extract_text(pdf_path, record)
    row["text"] = str(text_path.relative_to(REPO_ROOT)) if text_path else None
    return row


def extract_text(pdf_path: Path, record: dict) -> Path | None:
    try:
        from experteye_scraper.extraction.pdf_pipeline import extract_text as ee_extract
        text = ee_extract(pdf_path)
    except Exception:
        return None
    if not text or len(text) < 500:
        return None
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    out = TEXT_DIR / f"{slug(record)}.txt"
    out.write_text(text, encoding="utf-8")
    return out


def pending(corpus: Path) -> list[dict]:
    done = {r["record_id"] for r in read_jsonl(LEDGER) if r["status"] == "retrieved"}
    return [r for r in read_jsonl(corpus)
            if r.get("phase") in (PrismaPhase.screened_in.value, PrismaPhase.fulltext_sought.value)
            and r["id"] not in done]


def run(corpus: Path, *, limit: int | None = None, workers: int = 4, dry_run: bool = False) -> dict:
    todo = pending(corpus)[: limit or None]
    if dry_run:
        prefixes: dict[str, int] = {}
        for r in todo:
            p = (r.get("doi") or "no-doi").split("/")[0]
            prefixes[p] = prefixes.get(p, 0) + 1
        return {"would_try": len(todo), "with_arxiv_id": sum(bool(r.get("arxiv_id")) for r in todo),
                "doi_prefixes": dict(sorted(prefixes.items(), key=lambda kv: -kv[1])[:15])}
    cfg = load_tdm_config()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool, LEDGER.open("a", encoding="utf-8") as fh:
        for row in pool.map(lambda r: acquire(r, cfg), todo):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            key = row["route"] or "not_retrieved"
            stats[key] = stats.get(key, 0) + 1
    apply(corpus)
    return {"attempted": len(todo), "by_route": stats}


def finalize(corpus: Path) -> int:
    """After tier 3: records still without full text become `fulltext_not_retrieved` (PRISMA)."""

    with locked(corpus):
        return _finalize(corpus)


def _finalize(corpus: Path) -> int:
    records = read_jsonl(corpus)
    n = 0
    for r in records:
        if r.get("phase") == PrismaPhase.fulltext_sought.value:
            r["phase"] = PrismaPhase.fulltext_not_retrieved.value
            n += 1
    rewrite_jsonl(corpus, records)
    return n


def text_for(record: dict) -> str | None:
    p = record.get("fulltext_txt_path")
    return (REPO_ROOT / p).read_text(encoding="utf-8") if p and (REPO_ROOT / p).exists() else None


def apply(corpus: Path) -> int:
    """Copy the latest acquisition outcome per record into the corpus and advance phases."""

    with locked(corpus):
        return _apply(corpus)


def _apply(corpus: Path) -> int:
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    records = read_jsonl(corpus)
    n = 0
    for r in records:
        a = latest.get(r["id"])
        if not a or r.get("phase") not in (PrismaPhase.screened_in.value, PrismaPhase.fulltext_sought.value,
                                           PrismaPhase.fulltext_not_retrieved.value):
            continue
        if a["status"] == "retrieved":
            r.update(local_pdf_path=a["pdf"], checksum=a["sha256"], byte_count=a["bytes"], access_route=a["route"],
                     acquisition_status="retrieved", fulltext_txt_path=a.get("text"), phase=PrismaPhase.assessed.value)
        else:
            # Kept as sought (not final) until tier 3 has been tried; `finalize` marks the rest not retrieved.
            r.update(acquisition_status="not_retrieved", failure_reason=",".join(a["tried"]),
                     phase=PrismaPhase.fulltext_sought.value)
        n += 1
    rewrite_jsonl(corpus, records)
    return n
