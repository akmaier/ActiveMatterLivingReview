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
import html
import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import REPO_ROOT, TdmConfig, load_tdm_config
from ..schema import PrismaPhase
from ..search import MAILTO, require_mailto
from ..storage import locked, read_jsonl, rewrite_jsonl
from .pdftext import extract_text as pdf_text

PDF_DIR = REPO_ROOT / "docs"
TEXT_DIR = REPO_ROOT / "data" / "fulltext_text"
LEDGER = REPO_ROOT / "data" / "fulltext" / "acquisition.jsonl"
MIN_PDF_BYTES = 10_000
UA = f"amlr/0.0.1 (+https://github.com/akmaier/ActiveMatterLivingReview; mailto:{MAILTO})"

_last: dict[str, float] = {}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _polite(host: str, interval: float) -> None:
    """Per-host spacing that holds across worker threads."""

    with _locks_guard:
        lock = _locks.setdefault(host, threading.Lock())
    with lock:
        wait = _last.get(host, 0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.monotonic()


class Inconclusive(RuntimeError):
    """A route could not be checked (rate limit, outage); it must not count as tried."""


def _get_backoff(url: str, host: str, interval: float, headers: dict | None = None,
                 tries: int = 4, timeout: int = 60) -> tuple[int, bytes, str]:
    for attempt in range(tries):
        _polite(host, interval)
        code, data, ct = _get(url, headers, timeout=timeout)
        if code not in (429, 503) and code != 0:
            return code, data, ct
        time.sleep(min(300, 15 * 2**attempt))
    raise Inconclusive(f"{host}: HTTP {code} after {tries} attempts")


_net = threading.local()


def _get(url: str, headers: dict | None = None, timeout: int = 60) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    _net.failures = getattr(_net, "failures", 0)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        # No HTTP response (broken transfer, reset, timeout): counted so the route is "inconclusive".
        _net.failures = getattr(_net, "failures", 0) + 1
        return 0, b"", ""


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-" and len(data) >= MIN_PDF_BYTES


def pdf_pages(data: bytes) -> int:
    try:
        import pymupdf

        return pymupdf.open(stream=data, filetype="pdf").page_count
    except Exception:
        return 0


def slug(record: dict) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", record["id"])[:150]


# ---------------------------------------------------------------- routes (bytes or None)

class XmlText(bytes):
    """Full text delivered as publisher XML instead of PDF (stored as docs/<slug>.xml)."""


_ELS_DROP = re.compile(r"<(ce:cross-refs?|ce:cross-ref|mml:math|ce:inline-figure)[^>]*>.*?</\1>", re.S)


def elsevier_xml_text(xml: str) -> str:
    """Plain text from Elsevier full-text XML: title, abstract, section titles and body, captions."""

    def strip(fragment: str) -> str:
        fragment = _ELS_DROP.sub(" ", fragment)
        fragment = re.sub(r"</(ce:para|ce:section-title|ce:simple-para|ce:caption)>", "\n", fragment)
        return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment)))

    parts = []
    for tag in ("dc:title", "dc:description", "ce:abstract-sec", "ce:sections", "ce:caption"):
        parts += [strip(m) for m in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.S)]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def r_elsevier(doi: str, cfg) -> bytes | None:
    """Elsevier Article Retrieval API, full-text XML (view=FULL).

    With an API key and FAU's IP entitlement the XML carries the whole article; the PDF
    rendition is restricted to the first page unless an institutional token is configured.
    """

    if not doi.startswith("10.1016/") or not cfg.elsevier_api_key:
        return None
    h = {"X-ELS-APIKey": cfg.elsevier_api_key}
    if cfg.elsevier_insttoken:
        _polite("api.elsevier.com", 0.3)
        _, pdf, _ = _get(f"https://api.elsevier.com/content/article/doi/{doi}",
                         h | {"X-ELS-Insttoken": cfg.elsevier_insttoken, "Accept": "application/pdf"})
        if is_pdf(pdf) and pdf_pages(pdf) > 1:
            return pdf
    _polite("api.elsevier.com", 0.3)
    code, xml, _ = _get(f"https://api.elsevier.com/content/article/doi/{doi}?view=FULL", h | {"Accept": "text/xml"})
    if code == 200 and b"<ce:sections" in xml and len(elsevier_xml_text(xml.decode("utf-8", "replace"))) > 5000:
        return XmlText(xml)
    return None


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
    locs = [meta.get("best_oa_location") or {}] + (meta.get("oa_locations") or [])
    for url in dict.fromkeys(u for u in (loc.get("url_for_pdf") for loc in locs) if u):
        _polite(urllib.parse.urlparse(url).netloc, 1.0)
        _, pdf, _ = _get(url, {"Accept": "application/pdf"})
        if is_pdf(pdf):
            return pdf
    # Repository copies (HAL, institutional repositories) are often listed only by landing page.
    for url in dict.fromkeys(loc.get("url") for loc in locs if loc.get("url") and not loc.get("url_for_pdf")):
        if "doi.org/" in url or "/pmc/articles/" in url:
            continue  # publisher pages and PMC have their own routes
        host = urllib.parse.urlparse(url).netloc
        _polite(host, 1.0)
        _, page, _ = _get(url, {"Accept": "text/html"}, timeout=30)
        m = _META.search(page)
        if m:
            pdf_url = urllib.parse.urljoin(url, (m.group(1) or m.group(2)).decode(errors="ignore"))
            _polite(urllib.parse.urlparse(pdf_url).netloc, 1.0)
            _, pdf, _ = _get(pdf_url, {"Accept": "application/pdf"})
            if is_pdf(pdf):
                return pdf
    return None


_OA_LOCATIONS: dict[str, list[str]] | None = None


def openalex_locations(work_id: str) -> list[str]:
    """PDF and landing-page URLs OpenAlex lists for a work (from the stored raw retrieval)."""

    global _OA_LOCATIONS
    if _OA_LOCATIONS is None:
        _OA_LOCATIONS = {}
        for raw in sorted((REPO_ROOT / "data" / "raw").glob("openalex-*.raw.jsonl")):
            with raw.open(encoding="utf-8") as fh:
                for line in fh:
                    w = json.loads(line)
                    locs = [w.get("best_oa_location") or {}] + (w.get("locations") or [])
                    urls = [u for loc in locs for u in (loc.get("pdf_url"), loc.get("landing_page_url")) if u]
                    _OA_LOCATIONS[w["id"].rsplit("/", 1)[-1]] = list(dict.fromkeys(urls))
    return _OA_LOCATIONS.get(work_id, [])


def r_openalex_locations(work_id: str, cfg) -> bytes | None:
    for url in openalex_locations(work_id):
        if "doi.org/" in url:
            continue  # DOI landing pages are covered by the DOI routes
        host = urllib.parse.urlparse(url).netloc
        _polite(host, 1.0)
        _, data, _ = _get(url, {"Accept": "application/pdf,text/html"}, timeout=60)
        if is_pdf(data):
            return data
        m = _META.search(data)
        if m:
            pdf_url = urllib.parse.urljoin(url, (m.group(1) or m.group(2)).decode(errors="ignore"))
            _polite(urllib.parse.urlparse(pdf_url).netloc, 1.0)
            _, pdf, _ = _get(pdf_url, {"Accept": "application/pdf"})
            if is_pdf(pdf):
                return pdf
    return None


def r_hal(docid: str, cfg) -> bytes | None:
    """PDF deposited in HAL (open archive), via the HAL search API's files_s field."""

    _polite("api.archives-ouvertes.fr", 1.0)
    code, data, _ = _get("https://api.archives-ouvertes.fr/search/?" + urllib.parse.urlencode(
        {"q": f"docid:{docid}", "fl": "files_s", "wt": "json"}), timeout=30)
    try:
        docs = json.loads(data)["response"]["docs"] if code == 200 else []
    except (json.JSONDecodeError, KeyError):
        return None
    for url in (docs[0].get("files_s") or []) if docs else []:
        _polite(urllib.parse.urlparse(url).netloc, 1.0)
        _, pdf, _ = _get(url, {"Accept": "application/pdf"})
        if is_pdf(pdf):
            return pdf
    return None


def r_arxiv(arxiv_id: str, cfg) -> bytes | None:
    # arXiv asks automated clients to use export.arxiv.org at ≤ 1 request / 3 s.
    _, data, _ = _get_backoff(f"https://export.arxiv.org/pdf/{arxiv_id}", "export.arxiv.org", 3.0,
                              {"Accept": "application/pdf"})
    return data if is_pdf(data) else None


def s2_lookup(doi: str) -> dict:
    """Semantic Scholar record: externalIds.ArXiv and openAccessPdf.url, if any."""

    # Unauthenticated pool: about 1 request/s shared by all clients, hence the backoff.
    code, data, _ = _get_backoff(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}"
                                 "?fields=externalIds,openAccessPdf", "api.semanticscholar.org", 1.2, timeout=30)
    try:
        return json.loads(data) if code == 200 else {}
    except json.JSONDecodeError:
        return {}


def r_s2(doi: str, cfg) -> bytes | None:
    meta = s2_lookup(doi)
    url = (meta.get("openAccessPdf") or {}).get("url")
    if url:
        _polite(urllib.parse.urlparse(url).netloc, 1.0)
        _, pdf, _ = _get(url, {"Accept": "application/pdf"})
        if is_pdf(pdf):
            return pdf
    ax = (meta.get("externalIds") or {}).get("ArXiv")
    return r_arxiv(ax, cfg) if ax else None


def arxiv_id_by_title(title: str) -> str | None:
    """Exact-title arXiv lookup (normalized-title Jaccard ≥ 0.9) for preprints not linked by DOI."""

    import xml.etree.ElementTree as ET

    from ..dedup import jaccard

    # Exact-phrase ti:"..." queries silently return nothing for hyphenated titles, so require
    # each significant word instead and confirm the match by title similarity below.
    stop = {"with", "from", "that", "this", "their", "into", "using", "based", "under", "over", "via", "and", "for", "the"}
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title or "") if len(w) > 3 and w.lower() not in stop]
    if len(words) < 3:
        return None
    q = urllib.parse.urlencode({"search_query": " AND ".join(f"ti:{w}" for w in words[:8]), "max_results": 5})
    code, data, _ = _get_backoff(f"https://export.arxiv.org/api/query?{q}", "export.arxiv.org", 3.0)
    if code != 200:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in ET.fromstring(data).findall("a:entry", ns):
        if jaccard(" ".join((e.findtext("a:title", "", ns)).split()), title) >= 0.9:
            return re.sub(r"v\d+$", "", e.findtext("a:id", "", ns).rsplit("/abs/", 1)[-1])
    return None


class JatsText(XmlText):
    """Full text delivered as JATS XML (PubMed Central / Europe PMC)."""


def jats_text(xml: str) -> str:
    def strip(fragment: str) -> str:
        fragment = re.sub(r"<(xref|inline-formula|disp-formula)[^>]*>.*?</\1>", " ", fragment, flags=re.S)
        fragment = re.sub(r"</(p|title|caption)>", "\n", fragment)
        return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment)))

    parts = [strip(m) for tag in ("article-title", "abstract", "body") for m in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.S)]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def pmcid_for(doi: str) -> str | None:
    _polite("www.ncbi.nlm.nih.gov", 0.4)
    code, data, _ = _get("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?" + urllib.parse.urlencode(
        {"ids": doi, "format": "json", "tool": "amlr"}), timeout=30)
    try:
        recs = json.loads(data).get("records", []) if code == 200 else []
    except json.JSONDecodeError:
        return None
    return next((r["pmcid"] for r in recs if r.get("pmcid")), None)


def r_pmc(doi: str, cfg) -> bytes | None:
    """Open-access full text from PubMed Central, via Europe PMC's fullTextXML service."""

    pmcid = pmcid_for(doi)
    if not pmcid:
        return None
    _polite("www.ebi.ac.uk", 0.5)
    code, xml, _ = _get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML", timeout=60)
    if code == 200 and b"<body" in xml and len(jats_text(xml.decode("utf-8", "replace"))) > 5000:
        return JatsText(xml)
    return None


DOI_ROUTES: list[tuple[str, int, Callable]] = [
    ("elsevier_tdm", 1, r_elsevier), ("wiley_tdm", 1, r_wiley), ("springer", 1, r_springer),
    ("aps", 1, r_aps), ("landing_page", 1, r_landing), ("unpaywall", 2, r_unpaywall),
    ("pmc", 2, r_pmc), ("semantic_scholar", 2, r_s2),
]


def acquire(record: dict, cfg, skip: set[str] = frozenset()) -> dict:
    """Try routes in tier order; `skip` holds routes that already failed for this record.

    A route that raises `Inconclusive` (rate limit, outage) is not added to `tried`, so a later
    retry attempts it again.
    """

    doi = (record.get("doi") or "").lower()
    tried, inconclusive = sorted(skip), []
    data, route, tier = None, None, None

    def attempt(name: str, t: int, fn: Callable[[], bytes | None]) -> bool:
        nonlocal data, route, tier
        _net.failures = 0
        try:
            got = fn()
        except Inconclusive:
            inconclusive.append(name)
            return False
        if not got and _net.failures:
            # The route never got an answer (network trouble): retry it later instead of ruling it out.
            inconclusive.append(name)
            return False
        tried.append(name)
        if got:
            data, route, tier = got, name, t
        return bool(got)

    if doi and not doi.startswith("10.48550/"):
        for name, t, fn in DOI_ROUTES:
            if name not in skip and attempt(name, t, lambda fn=fn: fn(doi, cfg)):
                break
    oa_id = (record.get("source_ids") or {}).get("openalex")
    if not data and oa_id and "openalex_locations" not in skip:
        attempt("openalex_locations", 2, lambda: r_openalex_locations(oa_id, cfg))
    hal_id = (record.get("source_ids") or {}).get("hal")
    if not data and hal_id and "hal" not in skip:
        attempt("hal", 2, lambda: r_hal(hal_id, cfg))
    if not data and record.get("arxiv_id") and "arxiv" not in skip:
        attempt("arxiv", 2, lambda: r_arxiv(record["arxiv_id"], cfg))
    if not data and not record.get("arxiv_id") and "arxiv_title" not in skip:
        def by_title() -> bytes | None:
            ax = arxiv_id_by_title(record.get("title") or "")
            return r_arxiv(ax, cfg) if ax else None
        attempt("arxiv_title", 2, by_title)
    row = {"record_id": record["id"], "doi": doi or None, "tried": tried, "inconclusive": inconclusive,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not data:
        return row | {"status": "not_retrieved", "route": None, "tier": None}
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    is_xml = isinstance(data, XmlText)
    pdf_path = PDF_DIR / f"{slug(record)}.{'xml' if is_xml else 'pdf'}"
    pdf_path.write_bytes(data)
    row |= {"status": "retrieved", "route": route, "tier": tier, "pdf": str(pdf_path.relative_to(REPO_ROOT)),
            "format": "xml" if is_xml else "pdf", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    text_path = extract_text(pdf_path, record)
    row["text"] = str(text_path.relative_to(REPO_ROOT)) if text_path else None
    return row


def extract_text(pdf_path: Path, record: dict) -> Path | None:
    try:
        if pdf_path.suffix == ".xml":
            raw = pdf_path.read_text(encoding="utf-8", errors="replace")
            text = elsevier_xml_text(raw) if "<ce:sections" in raw else jats_text(raw)
        else:
            text = pdf_text(pdf_path)
    except Exception:
        return None
    if not text or len(text) < 500:
        return None
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    out = TEXT_DIR / f"{slug(record)}.txt"
    out.write_text(text, encoding="utf-8")
    return out


def pending(corpus: Path, only_new_routes: bool = False) -> list[dict]:
    """Records still needing full text. `only_new_routes`: skip records whose last attempt
    already tried every current route (avoids re-hitting publishers that refused)."""

    rows = read_jsonl(LEDGER)
    latest = {r["record_id"]: r for r in rows}  # an invalidation row supersedes an earlier retrieval
    done = {rid for rid, r in latest.items() if r["status"] == "retrieved"}
    last = {rid: set(r.get("tried", [])) for rid, r in latest.items()}
    current = {name for name, _, _ in DOI_ROUTES} | {"openalex_locations", "hal", "arxiv", "arxiv_title"}
    out = []
    for r in read_jsonl(corpus):
        if r.get("phase") not in (PrismaPhase.screened_in.value, PrismaPhase.fulltext_sought.value) or r["id"] in done:
            continue
        if only_new_routes and r["id"] in last and not (current - last[r["id"]]):
            continue
        out.append(r)
    return out


def run(corpus: Path, *, limit: int | None = None, workers: int = 4, dry_run: bool = False,
        retry: bool = False, force_routes: frozenset[str] = frozenset()) -> dict:
    """`retry`: only records not yet retrieved, trying only routes they have not tried.
    `force_routes`: routes to attempt again even if recorded as tried."""

    if not dry_run:
        require_mailto()  # Unpaywall refuses requests without the caller's own address
    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    last = {rid: set(r.get("tried", [])) - set(force_routes) for rid, r in latest.items()} if retry else {}
    todo = [r for r in pending(corpus, only_new_routes=retry and not force_routes)
            if not retry or not force_routes or r["id"] not in last
            or (force_routes - last.get(r["id"], set()))][: limit or None]
    if dry_run:
        prefixes: dict[str, int] = {}
        for r in todo:
            p = (r.get("doi") or "no-doi").split("/")[0]
            prefixes[p] = prefixes.get(p, 0) + 1
        return {"would_try": len(todo), "with_arxiv_id": sum(bool(r.get("arxiv_id")) for r in todo),
                "doi_prefixes": dict(sorted(prefixes.items(), key=lambda kv: -kv[1])[:15])}
    try:
        cfg = load_tdm_config()
    except FileNotFoundError:  # e.g. a CI runner: open-access routes only, TDM routes return nothing
        cfg = TdmConfig(source_path=Path("(none)"))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool, LEDGER.open("a", encoding="utf-8") as fh:
        for row in pool.map(lambda r: acquire(r, cfg, last.get(r["id"], frozenset())), todo):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            key = row["route"] or "not_retrieved"
            stats[key] = stats.get(key, 0) + 1
    apply(corpus)
    return {"attempted": len(todo), "by_route": stats}


def invalidate(corpus: Path, record_ids: list[str], reason: str) -> int:
    """Withdraw retrieved full texts that turned out unusable (e.g. one-page previews).

    Deletes the PDF and text, records a `not_retrieved` row whose `tried` keeps the failed route
    (so retries skip it), returns the record to `fulltext_sought`, and appends an invalidation
    marker to the full-text vote ledger so votes cast on the bad text no longer count.
    """

    from ..screen_llm import _ledger_path
    from ..schema import Stage

    latest = {r["record_id"]: r for r in read_jsonl(LEDGER)}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    with locked(corpus):
        records = read_jsonl(corpus)
        for r in records:
            if r["id"] not in record_ids:
                continue
            a = latest.get(r["id"], {})
            for f in (a.get("pdf"), a.get("text")):
                if f and (REPO_ROOT / f).exists():
                    (REPO_ROOT / f).unlink()
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"record_id": r["id"], "doi": r.get("doi"), "status": "not_retrieved",
                                     "route": None, "tier": None, "tried": sorted(set(a.get("tried", [])) | {a.get("route")} - {None}),
                                     "invalidated": reason, "at": now}) + "\n")
            ft = _ledger_path(Stage.full_text)
            ft.parent.mkdir(parents=True, exist_ok=True)
            with ft.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"record_id": r["id"], "stage": "full_text", "invalidated_at": now,
                                     "reason": reason}) + "\n")
            for f in ("local_pdf_path", "checksum", "byte_count", "access_route", "fulltext_txt_path"):
                r.pop(f, None)
            r.update(phase=PrismaPhase.fulltext_sought.value, acquisition_status="not_retrieved",
                     failure_reason=reason, decisions=[d for d in r.get("decisions", []) if d.get("stage") != "full_text"])
            n += 1
        rewrite_jsonl(corpus, records)
    return n


def mark_no_full_report(corpus: Path, record_ids: list[str], reason: str) -> int:
    """Records whose only report is an abstract (e.g. conference abstracts): nothing to retrieve.
    PRISMA counts them as reports not retrieved, with this reason."""

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    with locked(corpus):
        records = read_jsonl(corpus)
        for r in records:
            if r["id"] in record_ids and r.get("phase") == PrismaPhase.fulltext_sought.value:
                r.update(phase=PrismaPhase.fulltext_not_retrieved.value, acquisition_status="no_full_report",
                         failure_reason=reason)
                with LEDGER.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"record_id": r["id"], "doi": r.get("doi"), "status": "no_full_report",
                                         "route": None, "tier": None, "tried": [], "reason": reason, "at": now}) + "\n")
                n += 1
        rewrite_jsonl(corpus, records)
    return n


def mark_abstract_only(corpus: Path, record_ids: list[str], reason: str) -> dict:
    """Assess eligibility on the abstract where no full text can be obtained (author decision,
    PROTOCOL amendment log). Records without an abstract stay `fulltext_not_retrieved`."""

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    done, no_abstract = 0, 0
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    with locked(corpus):
        records = read_jsonl(corpus)
        with LEDGER.open("a", encoding="utf-8") as fh:
            for r in records:
                if r["id"] not in record_ids or r.get("phase") not in (PrismaPhase.fulltext_sought.value,
                                                                       PrismaPhase.fulltext_not_retrieved.value):
                    continue
                if not r.get("abstract"):
                    why = f"{reason}; no abstract"
                    r.update(phase=PrismaPhase.fulltext_not_retrieved.value, acquisition_status="unobtainable",
                             failure_reason=why)
                    fh.write(json.dumps({"record_id": r["id"], "doi": r.get("doi"), "status": "unobtainable",
                                         "route": None, "tier": None, "tried": [], "reason": why, "at": now}) + "\n")
                    no_abstract += 1
                    continue
                path = TEXT_DIR / f"{slug(r)}.abstract.txt"
                path.write_text(f"{r.get('title', '')}\n\n[ABSTRACT ONLY - full text unavailable]\n\n{r['abstract']}\n",
                                encoding="utf-8")
                rel = str(path.relative_to(REPO_ROOT))
                fh.write(json.dumps({"record_id": r["id"], "doi": r.get("doi"), "status": "abstract_only",
                                     "route": None, "tier": None, "tried": [], "reason": reason, "text": rel,
                                     "at": now}) + "\n")
                r.update(phase=PrismaPhase.assessed.value, assessment_basis="abstract_only",
                         acquisition_status="abstract_only", failure_reason=reason, fulltext_txt_path=rel,
                         decisions=[x for x in r.get("decisions", []) if x.get("stage") != "full_text"])
                done += 1
        rewrite_jsonl(corpus, records)
    return {"abstract_only": done, "no_abstract_not_retrieved": no_abstract}


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
        if a["status"] == "unobtainable":
            r.update(acquisition_status="unobtainable", failure_reason=a.get("reason"),
                     phase=PrismaPhase.fulltext_not_retrieved.value)
        elif a["status"] == "abstract_only":
            r.update(acquisition_status="abstract_only", assessment_basis="abstract_only",
                     failure_reason=a.get("reason"), fulltext_txt_path=a.get("text"),
                     phase=PrismaPhase.assessed.value)
        elif a["status"] == "no_full_report":
            r.update(acquisition_status="no_full_report", failure_reason=a.get("reason"),
                     phase=PrismaPhase.fulltext_not_retrieved.value)
        elif a["status"] == "retrieved":
            r.update(local_pdf_path=a["pdf"], checksum=a["sha256"], byte_count=a["bytes"], access_route=a["route"],
                     acquisition_status="retrieved", fulltext_txt_path=a.get("text"), phase=PrismaPhase.assessed.value)
        else:
            # Kept as sought (not final) until tier 3 has been tried; `finalize` marks the rest not retrieved.
            r.update(acquisition_status="not_retrieved", failure_reason=",".join(a["tried"]),
                     phase=PrismaPhase.fulltext_sought.value)
        n += 1
    rewrite_jsonl(corpus, records)
    return n
