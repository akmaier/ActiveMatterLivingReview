"""Per-source record retrieval. Each run writes, under data/raw/:

  <source>-<date>.raw.jsonl   raw payload items (one per line, as returned)
  <source>-<date>.jsonl       normalized records (amlr.schema.Record shape)

and a dated strategy file under protocol/search_strategies/ with the query, counts, and
payload hash.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Callable, Iterator

from . import search
from .search import (
    ARXIV_RPS, MAILTO, RAW, pubmed_window, window_note, STRATEGIES, SYNTAX, _abstract_from_inverted, ads_token, ads_url, arxiv_url,
    europepmc_url, hal_url, http, load_concepts, matches, openalex_url, render, require_mailto, write_strategy,
)

Item = tuple[dict, dict]  # (normalized record, raw item)


# ---------------------------------------------------------------- OpenAlex (credit-metered)

class CreditsExhausted(RuntimeError):
    pass


def _openalex_get(url: str, *, min_remaining: int = 20) -> dict:
    """GET without the HttpClient's Retry-After sleep: OpenAlex answers 429 with resets of hours."""

    req = urllib.request.Request(url, headers={"User-Agent": f"amlr/0.0.1 (mailto:{MAILTO})"})
    for attempt in range(6):
        time.sleep(1.0)  # OpenAlex also enforces a short-term burst limit on search requests
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                remaining = int(r.headers.get("x-ratelimit-remaining", "1000000"))
                data = json.load(r)
            if remaining < min_remaining:
                data["_amlr_stop"] = f"credits nearly exhausted ({remaining} left)"
            return data
        except urllib.error.HTTPError as e:
            remaining = e.headers.get("x-ratelimit-remaining")
            if e.code == 429 and remaining is not None and int(remaining) < min_remaining:
                raise CreditsExhausted(f"OpenAlex daily credits exhausted; reset in {e.headers.get('x-ratelimit-reset')} s") from e
            if (e.code == 429 or e.code >= 500) and attempt < 5:
                # Burst limit (credits remain) or transient server error: back off and retry.
                wait = int(e.headers.get("Retry-After") or 0) or min(120, 15 * 2**attempt)
                time.sleep(wait)
                continue
            if e.code == 429:
                raise CreditsExhausted(f"OpenAlex 429 persisted after backoff (remaining={remaining})") from e
            raise
    raise AssertionError("unreachable")


def _openalex_record(w: dict) -> dict:
    loc = (w.get("primary_location") or {}).get("source") or {}
    wid = w["id"].rsplit("/", 1)[-1]
    return {
        "id": f"openalex:{wid}",
        "title": w.get("display_name") or "",
        "authors": [a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
        "year": w.get("publication_year"),
        "venue": loc.get("display_name"),
        "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
        "abstract": _abstract_from_inverted(w.get("abstract_inverted_index")),
        "keywords": [k["display_name"] for k in w.get("keywords", []) if k.get("display_name")],
        "type": w.get("type"),
        "source_ids": {"openalex": wid},
    }


def fetch_openalex(out_dir: Path = RAW) -> dict:
    """Resumable: the next cursor is checkpointed after every page; rerun to continue."""

    q = render(load_concepts(), SYNTAX["openalex"])
    state_path = out_dir / "openalex.state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("query") != q or state.get("done"):
        state = {"query": q, "cursor": "*", "started": _now().isoformat(timespec="seconds"),
                 "stamp": _now().date().isoformat(), "n": 0, "done": False}
    raw_path = out_dir / f"openalex-{state['stamp']}.raw.jsonl"
    rec_path = out_dir / f"openalex-{state['stamp']}.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    stop = None
    try:
        while state["cursor"]:
            page = _openalex_get(openalex_url(q, per_page=200, cursor=state["cursor"]))
            with raw_path.open("a", encoding="utf-8") as rf, rec_path.open("a", encoding="utf-8") as pf:
                for w in page["results"]:
                    rf.write(json.dumps(w, ensure_ascii=False, sort_keys=True) + "\n")
                    rec = _openalex_record(w) | {"provenance": _prov("openalex", state["stamp"])}
                    pf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            state["n"] += len(page["results"])
            state["cursor"] = page["meta"].get("next_cursor") if page["results"] else None
            state_path.write_text(json.dumps(state, indent=2))
            if page.get("_amlr_stop"):
                stop = page["_amlr_stop"]
                break
    except CreditsExhausted as e:
        stop = str(e)
    if stop:
        return {"source": "openalex", "records_so_far": state["n"], "paused": stop,
                "resume": "rerun `amlr fetch openalex` after the credit reset"}
    state["done"] = True
    state_path.write_text(json.dumps(state, indent=2))
    sha = _file_sha(raw_path)
    write_strategy("openalex", q + window_note(), state["n"], sha, datetime.fromisoformat(state["started"]))
    return {"source": "openalex", "records": state["n"], "records_file": str(rec_path)}


# ---------------------------------------------------------------- arXiv

_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom",
         "os": "http://a9.com/-/spec/opensearch/1.1/"}


def _arxiv_items(q: str) -> Iterator[Item]:
    client = http(ARXIV_RPS, retries=6)
    start, page_size, total = 0, 200, None
    while total is None or start < total:
        root = ET.fromstring(client.fetch_text(arxiv_url(q, start=start, max_results=page_size)))
        total = int(root.find("os:totalResults", _ATOM).text)
        entries = root.findall("a:entry", _ATOM)
        if not entries:
            break
        for e in entries:
            abs_id = e.find("a:id", _ATOM).text.rsplit("/abs/", 1)[-1]
            base_id = re.sub(r"v\d+$", "", abs_id)
            doi = e.find("arxiv:doi", _ATOM)
            jref = e.find("arxiv:journal_ref", _ATOM)
            text = lambda tag: " ".join((e.find(tag, _ATOM).text or "").split())
            raw = {"arxiv_id": abs_id, "title": text("a:title"), "summary": text("a:summary"),
                   "published": e.find("a:published", _ATOM).text,
                   "authors": [a.find("a:name", _ATOM).text for a in e.findall("a:author", _ATOM)],
                   "categories": [c.get("term") for c in e.findall("a:category", _ATOM)],
                   "doi": doi.text if doi is not None else None,
                   "journal_ref": jref.text if jref is not None else None}
            yield {
                "id": f"arxiv:{base_id}", "title": raw["title"], "authors": raw["authors"],
                "year": int(raw["published"][:4]), "venue": raw["journal_ref"] or "arXiv",
                "doi": raw["doi"], "arxiv_id": base_id, "abstract": raw["summary"],
                "keywords": raw["categories"], "type": "preprint", "source_ids": {"arxiv": base_id},
            }, raw
        start += len(entries)


# ---------------------------------------------------------------- PubMed

def _pubmed_items(q: str) -> Iterator[Item]:
    client = http(3.0)
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    es = client.fetch_json(base + "esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": q, "retmode": "json", "usehistory": "y", "retmax": 0, "tool": "amlr"}
        | pubmed_window()))["esearchresult"]
    total, webenv, key = int(es["count"]), es["webenv"], es["querykey"]
    for start in range(0, total, 200):
        xml_text = client.fetch_text(base + "efetch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "WebEnv": webenv, "query_key": key, "retstart": start, "retmax": 200,
             "retmode": "xml", "tool": "amlr"}))
        for art in ET.fromstring(xml_text).findall("PubmedArticle"):
            pmid = art.findtext("MedlineCitation/PMID")
            a = art.find("MedlineCitation/Article")
            title = "".join(a.find("ArticleTitle").itertext()) if a is not None else ""
            abstract = " ".join("".join(t.itertext()) for t in a.findall("Abstract/AbstractText")) if a is not None else ""
            authors = [f"{x.findtext('ForeName', '')} {x.findtext('LastName', '')}".strip()
                       for x in (a.findall("AuthorList/Author") if a is not None else [])]
            year = art.findtext("MedlineCitation/Article/Journal/JournalIssue/PubDate/Year") or \
                (art.findtext("MedlineCitation/Article/Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
            doi = next((i.text for i in art.findall("PubmedData/ArticleIdList/ArticleId") if i.get("IdType") == "doi"), None)
            kws = [k.text for k in art.findall("MedlineCitation/KeywordList/Keyword") if k.text]
            raw = {"pmid": pmid, "xml": ET.tostring(art, encoding="unicode")}
            yield {
                "id": f"pmid:{pmid}", "title": title, "authors": [x for x in authors if x],
                "year": int(year) if str(year).isdigit() else None,
                "venue": art.findtext("MedlineCitation/Article/Journal/Title"), "doi": doi, "pmid": pmid,
                "abstract": abstract or None, "keywords": kws, "type": "article", "source_ids": {"pubmed": pmid},
            }, raw


# ---------------------------------------------------------------- HAL

def _hal_items(q: str) -> Iterator[Item]:
    client = http(3.0)
    start, rows = 0, 500
    while True:
        resp = client.fetch_json(hal_url(q, rows=rows, start=start))["response"]
        for d in resp["docs"]:
            yield {
                "id": f"hal:{d['docid']}", "title": (d.get("title_s") or [""])[0],
                "authors": d.get("authFullName_s") or [], "year": d.get("producedDateY_i"),
                "venue": d.get("journalTitle_s"), "doi": d.get("doiId_s"),
                "abstract": (d.get("abstract_s") or [None])[0], "keywords": d.get("keyword_s") or [],
                "type": d.get("docType_s"), "source_ids": {"hal": str(d["docid"])},
            }, d
        start += rows
        if start >= resp["numFound"]:
            break


# ---------------------------------------------------------------- bioRxiv via Europe PMC

def _biorxiv_items(q: str) -> Iterator[Item]:
    client = http(3.0)
    cursor = "*"
    while True:
        page = client.fetch_json(europepmc_url(q, page_size=1000, cursor=cursor))
        for r in page.get("resultList", {}).get("result", []):
            yield {
                "id": f"epmc:{r['id']}", "title": r.get("title") or "",
                "authors": [a.strip() for a in (r.get("authorString") or "").rstrip(".").split(",") if a.strip()],
                "year": int(r["pubYear"]) if str(r.get("pubYear", "")).isdigit() else None,
                "venue": "bioRxiv", "doi": r.get("doi"), "abstract": r.get("abstractText"),
                "keywords": [], "type": "preprint", "source_ids": {"europepmc": r["id"]},
            }, r
        nxt = page.get("nextCursorMark")
        if not nxt or nxt == cursor or not page.get("resultList", {}).get("result"):
            break
        cursor = nxt


# ---------------------------------------------------------------- NASA ADS

def _ads_items(q: str) -> Iterator[Item]:
    client = http(2.0)
    headers = {"Authorization": f"Bearer {ads_token()}"}
    start, rows = 0, 2000
    while True:
        resp = client.fetch_json(ads_url(q, rows=rows, start=start), headers)["response"]
        for d in resp["docs"]:
            arxiv = next((i.split(":", 1)[1] for i in d.get("identifier", []) if i.lower().startswith("arxiv:")), None)
            yield {
                "id": f"ads:{d['bibcode']}", "title": (d.get("title") or [""])[0],
                "authors": d.get("author") or [], "year": int(d["year"]) if d.get("year") else None,
                "venue": d.get("pub"), "doi": (d.get("doi") or [None])[0], "arxiv_id": arxiv,
                "abstract": d.get("abstract"), "keywords": d.get("keyword") or [],
                "type": d.get("doctype"), "source_ids": {"ads": d["bibcode"]},
            }, d
        start += rows
        if start >= resp["numFound"]:
            break


# ---------------------------------------------------------------- IEEE Xplore (web export)

IEEE_EXPORTS = RAW / "ieee_exports"


def _ieee_items(export_dir: Path) -> Iterator[Item]:
    """Records from IEEE Xplore 'Export → Search Results → CSV' files (one per query)."""

    import csv

    for path in sorted(export_dir.glob("q*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                m = re.search(r"arnumber=(\d+)", row.get("PDF Link") or "")
                arnumber = m.group(1) if m else None
                doi = (row.get("DOI") or "").strip() or None
                key = arnumber or doi or "t" + hashlib.sha1((row.get("Document Title") or "").encode()).hexdigest()[:12]
                kws = [k.strip() for f in ("Author Keywords", "IEEE Terms")
                       for k in (row.get(f) or "").split(";") if k.strip()]
                year = (row.get("Publication Year") or "").strip()
                yield {
                    "id": f"ieee:{key}", "title": row.get("Document Title") or "",
                    "authors": [a.strip() for a in (row.get("Authors") or "").split(";") if a.strip()],
                    "year": int(year) if year.isdigit() else None, "venue": row.get("Publication Title"),
                    "doi": doi, "abstract": row.get("Abstract") or None, "keywords": kws,
                    "type": row.get("Document Identifier"),
                    "source_ids": {"ieee": key},
                }, row | {"_export_file": path.name}


def fetch_ieee(out: Path = RAW, export_date: str | None = None) -> dict:
    """Import the CSV exports saved under data/raw/ieee_exports/<date>/ (q1.csv = branch A, q2.csv = rest)."""

    from .search import render_ieee

    dirs = sorted(p for p in IEEE_EXPORTS.iterdir() if p.is_dir()) if IEEE_EXPORTS.exists() else []
    export_dir = IEEE_EXPORTS / export_date if export_date else (dirs[-1] if dirs else None)
    if not export_dir or not list(export_dir.glob("q*.csv")):
        raise FileNotFoundError("no IEEE exports found; export the two render_ieee() queries as CSV first")
    shas = {p.name: _file_sha(p) for p in sorted(export_dir.glob("q*.csv"))}
    queries = render_ieee(load_concepts())
    desc = ("IEEE Xplore Command Search (web UI, FAU institutional access), exported via "
            "Export → Search Results → CSV.\n" + "\n".join(f"q{i}: {q}" for i, q in enumerate(queries, 1))
            + f"\nexport files (sha256): {json.dumps(shas)}")
    return _run("ieee", _ieee_items(export_dir), desc, out)


# ---------------------------------------------------------------- Crossref (no Boolean search)

def crossref_subqueries(c: dict) -> list[str]:
    """Relevance queries for every AND-pair plus every phrase; results are filtered locally."""

    strip = lambda t: t.rstrip("*")
    pairs = [f"{strip(a)} {strip(b)}" for a, b in product(c["active_matter"], c["robotic_agents"])]
    pairs += [f"{strip(a)} {strip(b)}" for a, b in product(c["colloids"], c["control"])]
    return pairs + [strip(p) for p in c["composite_phrases"]]


_TAGS = re.compile(r"<[^>]+>")
# Crossref registers supplementary files, datasets, reviews, and containers that are not reports.
CROSSREF_NON_REPORT = {"component", "dataset", "peer-review", "grant", "database", "standard",
                       "journal", "journal-issue", "journal-volume", "proceedings", "book-series",
                       "report-series", "book-set"}
crossref_skipped: dict[str, int] = {}


def _crossref_items(c: dict, rows: int = 100) -> Iterator[Item]:
    client = http(3.0)
    seen: set[str] = set()
    crossref_skipped.clear()
    for sq in crossref_subqueries(c):
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"query.bibliographic": sq, "rows": rows, "mailto": MAILTO,
             **({"filter": f"from-index-date:{search.WINDOW}"} if search.WINDOW else {}),
             "select": "DOI,title,abstract,author,issued,container-title,type,subject"})
        for it in client.fetch_json(url)["message"]["items"]:
            doi = it["DOI"].lower()
            if doi in seen:
                continue
            if it.get("type") in CROSSREF_NON_REPORT:
                seen.add(doi)
                if matches(c, " ".join(it.get("title") or [])):
                    crossref_skipped[it["type"]] = crossref_skipped.get(it["type"], 0) + 1
                continue
            title = " ".join(it.get("title") or [])
            abstract = html.unescape(_TAGS.sub(" ", it.get("abstract") or "")).strip() or None
            if not matches(c, f"{title} {abstract or ''}"):
                continue
            seen.add(doi)
            issued = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
            yield {
                "id": f"crossref:{doi}", "title": title,
                "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in it.get("author", [])],
                "year": issued, "venue": (it.get("container-title") or [None])[0], "doi": doi,
                "abstract": abstract, "keywords": it.get("subject") or [], "type": it.get("type"),
                "source_ids": {"crossref": doi},
            }, it | {"_subquery": sq}


# ---------------------------------------------------------------- runner

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prov(source: str, stamp: str) -> dict:
    return {source: {"query_file": f"{source}-{stamp}.txt", "retrieved": stamp}}


def _file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _run(source: str, items: Iterator[Item], query: str, out_dir: Path) -> dict:
    run_at = _now()
    stamp = run_at.date().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path, rec_path = out_dir / f"{source}-{stamp}.raw.jsonl", out_dir / f"{source}-{stamp}.jsonl"
    n = 0
    with raw_path.open("w", encoding="utf-8") as rf, rec_path.open("w", encoding="utf-8") as pf:
        for rec, raw in items:
            rf.write(json.dumps(raw, ensure_ascii=False, sort_keys=True) + "\n")
            pf.write(json.dumps(rec | {"provenance": _prov(source, stamp)}, ensure_ascii=False) + "\n")
            n += 1
    write_strategy(source, query + window_note(), n, _file_sha(raw_path), run_at)
    return {"source": source, "records": n, "records_file": str(rec_path)}


# ---------------------------------------------------------------- reader submissions (pull requests)

SUBMISSIONS = RAW.parents[1] / "submissions"  # RAW is <repo>/data/raw


def _submission_items() -> Iterator[Item]:
    """Merged pull-request submissions (submissions/*.yml) as records identified via other methods.
    The abstract comes from Crossref where it has one; the submitter's `why` is kept separately and
    never shown to the screening panel."""

    import yaml

    client = http(1.0)
    for f in sorted(SUBMISSIONS.glob("*.y*ml")):
        if f.name == "TEMPLATE.yml":
            continue
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        doi = str(d.get("doi") or "").strip().lower().removeprefix("https://doi.org/") or None
        arxiv = str(d.get("arxiv") or "").strip() or None
        abstract = None
        if doi:
            try:
                msg = client.fetch_json(f"https://api.crossref.org/works/{doi}?mailto={MAILTO}")["message"]
                abstract = re.sub(r"<[^>]+>", " ", msg.get("abstract") or "").strip() or None
            except Exception:  # a missing abstract only means the liberal no-abstract rule applies
                pass
        authors = d.get("authors") or []
        yield {
            "id": f"doi:{doi}" if doi else f"arxiv:{arxiv}", "title": str(d.get("title") or ""),
            "authors": authors if isinstance(authors, list) else [a.strip() for a in str(authors).split(";")],
            "year": d.get("year"), "venue": d.get("venue"), "doi": doi, "arxiv_id": arxiv,
            "abstract": abstract, "keywords": [], "type": "submission",
            "source_ids": {"submission": f.name}, "submission": {"file": f.name, "why": d.get("why"),
                                                                  "submitted_by": d.get("submitted_by")},
        }, d


FETCHERS: dict[str, Callable[[Path], dict]] = {
    "openalex": fetch_openalex,
    "arxiv": lambda out: _run("arxiv", _arxiv_items(q := render(load_concepts(), SYNTAX["arxiv"])), q, out),
    "pubmed": lambda out: _run("pubmed", _pubmed_items(q := render(load_concepts(), SYNTAX["pubmed"])), q, out),
    "hal": lambda out: _run("hal", _hal_items(q := render(load_concepts(), SYNTAX["hal"])), q, out),
    "europepmc_biorxiv": lambda out: _run(
        "europepmc_biorxiv", _biorxiv_items(q := render(load_concepts(), SYNTAX["europepmc_biorxiv"])),
        f'({q}) AND (PUBLISHER:"bioRxiv")', out),
    "ads": lambda out: _run("ads", _ads_items(q := render(load_concepts(), SYNTAX["ads"])), q, out),
    "ieee": lambda out: fetch_ieee(out),
    "crossref": lambda out: _fetch_crossref(out),
    "submissions": lambda out: _run("submissions", _submission_items(),
                                    "Reader submissions merged via pull request (submissions/*.yml)", out),
}


def _fetch_crossref(out: Path) -> dict:
    c = load_concepts()
    desc = ("query.bibliographic, rows=100, one request per subquery, then local Boolean filter "
            "(amlr.search.matches) on title+abstract. Non-report types skipped: "
            + ", ".join(sorted(CROSSREF_NON_REPORT)) + ".\nSubqueries:\n" + "\n".join(crossref_subqueries(c)))
    result = _run("crossref", _crossref_items(c), desc, out)
    # Matching non-report items are removed before screening; PRISMA reports them as such.
    strategy = max(STRATEGIES.glob("crossref-*.txt"))
    strategy.write_text(strategy.read_text() + f"\nskipped_non_report_matching_title: {json.dumps(crossref_skipped)}\n")
    return result | {"skipped_non_report": dict(crossref_skipped)}


def fetch(source: str, out_dir: Path = RAW) -> dict:
    require_mailto()
    return FETCHERS[source](out_dir)
