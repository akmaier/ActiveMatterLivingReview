"""Render the frozen concept blocks into per-source queries; count and fetch records.

Logic (PROTOCOL §5): ((AM) AND (ROBOT)) OR ((COLLOID) AND (CONTROL)) OR (PHRASES).
Each source has its own syntax for fields, phrases, and truncation; `Syntax` captures that.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import yaml
from experteye_scraper.http import HttpClient, RateLimitConfig

from . import __version__
from .config import REPO_ROOT

CONCEPTS = REPO_ROOT / "protocol" / "search_strategies" / "concepts.yml"
STRATEGIES = CONCEPTS.parent
RAW = REPO_ROOT / "data" / "raw"
# Contact address for the OpenAlex/Crossref polite pools (approved by the author 2026-10-11).
MAILTO = os.environ.get("AMLR_MAILTO", "andreas.maier@fau.de").strip()


class PoliteClient(HttpClient):
    """experteye's HttpClient never records the last request time, so it never throttles."""

    def _rate_limit(self) -> None:
        super()._rate_limit()
        self._last_request = time.monotonic()


def http(rps: float = 3.0, retries: int = 3) -> PoliteClient:
    return PoliteClient("amlr", MAILTO or "unset",
                        RateLimitConfig(requests_per_sec=rps, max_retries=retries, timeout_sec=90))


# arXiv asks API clients for one request every 3 s and answers bursts with 503.
ARXIV_RPS = 1 / 3


def load_concepts(path: Path = CONCEPTS) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class Syntax:
    field: Callable[[str], str]  # wraps one rendered term with the source's field restriction
    wildcard_word: bool  # truncation supported on single words
    wildcard_phrase: bool  # truncation supported inside quoted phrases
    and_: str = "AND"
    or_: str = "OR"


def _term(t: str, s: Syntax) -> str:
    phrase = " " in t
    if t.endswith("*") and not (s.wildcard_phrase if phrase else s.wildcard_word):
        t = t.rstrip("*")
    return s.field(f'"{t}"' if phrase else t)


def _block(terms: list[str], s: Syntax) -> str:
    return "(" + f" {s.or_} ".join(_term(t, s) for t in terms) + ")"


def render(c: dict, s: Syntax) -> str:
    a = f"({_block(c['active_matter'], s)} {s.and_} {_block(c['robotic_agents'], s)})"
    b = f"({_block(c['colloids'], s)} {s.and_} {_block(c['control'], s)})"
    return f"{a} {s.or_} {b} {s.or_} {_block(c['composite_phrases'], s)}"


SYNTAX = {
    # OpenAlex stems search terms and has no truncation operator.
    "openalex": Syntax(field=lambda t: t, wildcard_word=False, wildcard_phrase=False),
    "arxiv": Syntax(field=lambda t: f"(ti:{t} OR abs:{t})", wildcard_word=True, wildcard_phrase=False),
    "pubmed": Syntax(field=lambda t: f"{t}[tiab]", wildcard_word=True, wildcard_phrase=True),
    "hal": Syntax(field=lambda t: f"(title_t:{t} OR abstract_t:{t})", wildcard_word=True, wildcard_phrase=False),
    "europepmc_biorxiv": Syntax(field=lambda t: f"(TITLE:{t} OR ABSTRACT:{t})", wildcard_word=True, wildcard_phrase=False),
    # ADS `abs:` covers title, abstract, and keywords.
    "ads": Syntax(field=lambda t: f"abs:{t}", wildcard_word=True, wildcard_phrase=False),
}

def subsumed_dropped(terms: list[str]) -> list[str]:
    """Drop phrases implied by a single-word truncated term in the same block (e.g. robot* ⊇ "swarm robot*")."""

    stems = [t[:-1] for t in terms if t.endswith("*") and " " not in t and "-" not in t]
    keep = []
    for t in terms:
        words = t.replace("-", " ").rstrip("*").split()
        if len(words) > 1 and any(w.startswith(s) for s in stems for w in words):
            continue
        keep.append(t)
    return keep


IEEE_MAX_TERMS_PER_CLAUSE = 25
IEEE_MAX_WILDCARDS = 10


def render_ieee(c: dict) -> list[str]:
    """IEEE Xplore Command Search strings (Abstract field), within its 25-term / 10-wildcard limits.

    Wildcards are kept only on single-word robot-type terms; other terms rely on IEEE's
    plural matching. Long blocks are split into OR-ed sub-clauses of ≤ 25 terms.
    """

    def term(t: str, wild: bool) -> str:
        phrase = " " in t or "-" in t
        t = t if (wild and t.endswith("*") and not phrase) else t.rstrip("*")
        return f'"Abstract":"{t}"' if " " in t or "-" in t else f'"Abstract":{t}'

    def clause(terms: list[str], wild: bool) -> str:
        chunks = [terms[i:i + IEEE_MAX_TERMS_PER_CLAUSE] for i in range(0, len(terms), IEEE_MAX_TERMS_PER_CLAUSE)]
        parts = ["(" + " OR ".join(term(t, wild) for t in ch) + ")" for ch in chunks]
        return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"

    robots = subsumed_dropped(c["robotic_agents"])
    q1 = f"{clause(c['active_matter'], False)} AND {clause(robots, True)}"
    q2 = (f"({clause(c['colloids'], False)} AND {clause(c['control'], False)}) OR "
          f"{clause(c['composite_phrases'], False)}")
    for q in (q1, q2):
        if q.count("*") > IEEE_MAX_WILDCARDS:
            raise ValueError(f"IEEE query has {q.count('*')} wildcards (limit {IEEE_MAX_WILDCARDS})")
    return [q1, q2]


ADS_TOKEN_FILE = Path.home() / ".config" / "amlr" / "ads_token"


def ads_token() -> str:
    """ADS_TOKEN env var, else `[ads].ads_token` in tdm_api.toml, else ~/.config/amlr/ads_token."""

    from .config import load_tdm_config

    tok = os.environ.get("ADS_TOKEN", "").strip()
    if not tok:
        try:
            tok = str((load_tdm_config().raw.get("ads") or {}).get("ads_token") or "").strip()
        except FileNotFoundError:
            tok = ""
    if not tok and ADS_TOKEN_FILE.exists():
        tok = ADS_TOKEN_FILE.read_text().strip()
    if not tok:
        raise RuntimeError("no ADS token: set ADS_TOKEN or [ads].ads_token in tdm_api.toml")
    return tok


def ads_url(q: str, *, rows: int = 0, start: int = 0) -> str:
    return "https://api.adsabs.harvard.edu/v1/search/query?" + urllib.parse.urlencode(
        {"q": q, "rows": rows, "start": start, "sort": "date desc",
         "fl": "bibcode,title,abstract,author,year,doi,pub,keyword,doctype,identifier"})


def openalex_url(q: str, *, per_page: int = 1, cursor: str | None = None) -> str:
    params = {"filter": f"title_and_abstract.search:{q}", "per-page": per_page}
    if cursor:
        params["cursor"] = cursor
    if MAILTO:
        params["mailto"] = MAILTO
    return "https://api.openalex.org/works?" + urllib.parse.urlencode(params)


def arxiv_url(q: str, *, start: int = 0, max_results: int = 1) -> str:
    return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "start": start, "max_results": max_results})


def pubmed_url(q: str, *, retmax: int = 0, retstart: int = 0) -> str:
    return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "term": q, "retmode": "json", "retmax": retmax, "retstart": retstart})


def hal_url(q: str, *, rows: int = 0, start: int = 0) -> str:
    return "https://api.archives-ouvertes.fr/search/?" + urllib.parse.urlencode(
        {"q": q, "rows": rows, "start": start, "wt": "json",
         "fl": "docid,doiId_s,title_s,abstract_s,authFullName_s,producedDateY_i,journalTitle_s,keyword_s,uri_s,docType_s"})


def europepmc_url(q: str, *, page_size: int = 1, cursor: str = "*") -> str:
    full = f'({q}) AND (PUBLISHER:"bioRxiv")'
    return "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(
        {"query": full, "format": "json", "pageSize": page_size, "cursorMark": cursor, "resultType": "core"})


def _atom_total(xml_text: str) -> int:
    ns = {"os": "http://a9.com/-/spec/opensearch/1.1/"}
    return int(ET.fromstring(xml_text).find("os:totalResults", ns).text)


def count(source: str, c: dict | None = None) -> dict:
    """One request per source: the hit count for the rendered query, plus the query itself."""

    c = c or load_concepts()
    q = render(c, SYNTAX[source])
    client = http(ARXIV_RPS, retries=6) if source == "arxiv" else http(3.0)
    if source == "openalex":
        n = client.fetch_json(openalex_url(q))["meta"]["count"]
    elif source == "arxiv":
        n = _atom_total(client.fetch_text(arxiv_url(q)))
    elif source == "pubmed":
        n = int(client.fetch_json(pubmed_url(q))["esearchresult"]["count"])
    elif source == "hal":
        n = client.fetch_json(hal_url(q))["response"]["numFound"]
    elif source == "europepmc_biorxiv":
        n = client.fetch_json(europepmc_url(q))["hitCount"]
    elif source == "ads":
        n = client.fetch_json(ads_url(q), {"Authorization": f"Bearer {ads_token()}"})["response"]["numFound"]
    else:
        raise ValueError(source)
    return {"source": source, "count": n, "query": q,
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _abstract_from_inverted(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = sorted((i, w) for w, idx in inv.items() for i in idx)
    return " ".join(w for _, w in pos)


_TOKEN = __import__("re").compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("-", " "))


def _word_match(pattern: str, token: str) -> bool:
    # Truncation (*) is a prefix match; otherwise allow plural suffixes, approximating stemming.
    if pattern.endswith("*"):
        return token.startswith(pattern[:-1])
    return token in (pattern, pattern + "s", pattern + "es")


def _term_in(term: str, toks: list[str]) -> bool:
    words = _tokens(term.rstrip("*")) or []
    if term.endswith("*") and words:
        words[-1] += "*"
    n = len(words)
    return any(all(_word_match(w, toks[i + k]) for k, w in enumerate(words)) for i in range(len(toks) - n + 1))


def matches(c: dict, text: str) -> bool:
    """Local evaluation of the frozen Boolean logic, for sources without server-side Boolean search."""

    toks = _tokens(text)
    any_ = lambda block: any(_term_in(t, toks) for t in c[block])
    return ((any_("active_matter") and any_("robotic_agents"))
            or (any_("colloids") and any_("control"))
            or any_("composite_phrases"))


SEED_SET = STRATEGIES / "seed_set.yml"


def validate_seed_set(path: Path = SEED_SET) -> list[dict]:
    """Known-item recall: is each seed paper retrieved by the OpenAlex and arXiv queries?"""

    import re

    c = load_concepts()
    q_oa, q_ax = render(c, SYNTAX["openalex"]), render(c, SYNTAX["arxiv"])
    oa, ax = http(5.0), http(ARXIV_RPS, retries=6)
    with path.open(encoding="utf-8") as fh:
        seed = yaml.safe_load(fh)["seed"]
    out = []
    for item in seed:
        title = item["title"]
        clean = re.sub(r"[,:;]", " ", title)
        hits = oa.fetch_json("https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"filter": f"title.search:{clean}", "per-page": 3}))["results"]
        w = next((h for h in hits if (h.get("display_name") or "").lower()[:25] == title.lower()[:25]), None)
        row = {"title": title, "openalex_id": None, "has_abstract": None, "openalex": None, "arxiv": None}
        if w:
            wid = w["id"].rsplit("/", 1)[-1]
            row.update(openalex_id=wid, has_abstract=bool(w.get("abstract_inverted_index")))
            row["openalex"] = oa.fetch_json("https://api.openalex.org/works?" + urllib.parse.urlencode(
                {"filter": f"openalex:{wid},title_and_abstract.search:{q_oa}", "per-page": 1}))["meta"]["count"] > 0
        ti = 'ti:"' + re.sub(r'["]', "", clean) + '"'
        if _atom_total(ax.fetch_text(arxiv_url(ti))):
            row["arxiv"] = _atom_total(ax.fetch_text(arxiv_url(f"({ti}) AND ({q_ax})"))) > 0
        out.append(row)
    return out


def write_strategy(source: str, query: str, n: int, payload_sha: str | None, run_at: datetime) -> Path:
    p = STRATEGIES / f"{source}-{run_at.date().isoformat()}.txt"
    p.write_text(
        f"source: {source}\nrun_at_utc: {run_at.isoformat(timespec='seconds')}\n"
        f"amlr_version: {__version__}\nrecord_count: {n}\n"
        f"raw_payload_sha256: {payload_sha or 'n/a (count only)'}\n"
        f"concepts_sha256: {hashlib.sha256(CONCEPTS.read_bytes()).hexdigest()}\n\nquery:\n{query}\n",
        encoding="utf-8",
    )
    return p
