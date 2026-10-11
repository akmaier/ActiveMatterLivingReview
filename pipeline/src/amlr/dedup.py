"""Cross-source deduplication into one record per report.

Records are linked (union-find) when they share a DOI, arXiv ID, PMID, or a normalized title
of ≥ 5 words with publication years within 3 years; near-identical titles (Jaccard ≥ 0.9,
compared within blocks of equal leading words) are linked too. A preprint and its journal
version therefore become one record carrying both identifiers.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

_DOI_PREFIX = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$")
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")
# Fields where a better source should win over the first record seen.
_SOURCE_PRIORITY = ["crossref", "openalex", "pubmed", "ads", "ieee", "hal", "arxiv", "europepmc", "scholar"]


def canonical_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    s = _DOI_PREFIX.sub("", doi.strip()).lower()
    return s or None


def normalized_title(title: str | None) -> str:
    if not title:
        return ""
    s = _PUNCT.sub(" ", title.lower())
    return _WS.sub(" ", s).strip()


def _tokens(title: str) -> set[str]:
    return {t for t in normalized_title(title).split() if len(t) > 2}


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _arxiv_id(r: dict) -> str | None:
    if r.get("arxiv_id"):
        return re.sub(r"v\d+$", "", str(r["arxiv_id"]).lower())
    m = _ARXIV_DOI.match(canonical_doi(r.get("doi")) or "")
    return m.group(1) if m else None


def record_keys(r: dict) -> list[str]:
    keys = []
    doi = canonical_doi(r.get("doi"))
    if doi and not _ARXIV_DOI.match(doi):
        keys.append(f"doi:{doi}")
    if ax := _arxiv_id(r):
        keys.append(f"arxiv:{ax}")
    if r.get("pmid"):
        keys.append(f"pmid:{r['pmid']}")
    for src, sid in (r.get("source_ids") or {}).items():
        keys.append(f"{src}:{sid}".lower())
    return keys


class _UF:
    def __init__(self) -> None:
        self.p: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.p[self.find(a)] = self.find(b)


def _years_close(a: dict, b: dict, tol: int = 3) -> bool:
    ya, yb = a.get("year"), b.get("year")
    return ya is None or yb is None or abs(int(ya) - int(yb)) <= tol


def cluster(records: list[dict], *, title_threshold: float = 0.9) -> list[list[dict]]:
    uf = _UF()
    owner: dict[str, int] = {}
    for i, r in enumerate(records):
        uf.find(i)
        for k in record_keys(r):
            if k in owner:
                uf.union(i, owner[k])
            else:
                owner[k] = i
    # Titles: exact normalized match (long titles only), then near matches within blocks.
    by_title: dict[str, list[int]] = defaultdict(list)
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        nt = normalized_title(r.get("title"))
        words = nt.split()
        if len(words) >= 5:
            by_title[nt].append(i)
            blocks[" ".join(words[:3])].append(i)
    for idx in by_title.values():
        for j in idx[1:]:
            if _years_close(records[idx[0]], records[j]):
                uf.union(idx[0], j)
    for idx in blocks.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if uf.find(i) != uf.find(j) and _years_close(records[i], records[j]) and \
                        jaccard(records[i]["title"], records[j]["title"]) >= title_threshold:
                    uf.union(i, j)
    groups: dict[int, list[dict]] = defaultdict(list)
    for i, r in enumerate(records):
        groups[uf.find(i)].append(r)
    return list(groups.values())


def _source_of(r: dict) -> str:
    return next(iter(r.get("source_ids") or {"?": ""}))


def _rank(r: dict) -> int:
    s = _source_of(r)
    return _SOURCE_PRIORITY.index(s) if s in _SOURCE_PRIORITY else len(_SOURCE_PRIORITY)


def fold(group: list[dict]) -> dict:
    """One record per cluster: best-ranked source first; journal DOI over arXiv DOI; longest abstract."""

    group = sorted(group, key=_rank)
    out = dict(group[0])
    source_ids: dict[str, str] = {}
    provenance: dict = {}
    dois: set[str] = set()
    for r in group:
        for k, v in r.items():
            if out.get(k) in (None, "", [], {}):
                out[k] = v
        source_ids.update(r.get("source_ids") or {})
        provenance.update(r.get("provenance") or {})
        if d := canonical_doi(r.get("doi")):
            dois.add(d)
    journal = sorted(d for d in dois if not _ARXIV_DOI.match(d))
    out["doi"] = journal[0] if journal else (sorted(dois)[0] if dois else None)
    out["all_dois"] = sorted(dois)
    out["arxiv_id"] = next((a for a in map(_arxiv_id, group) if a), None)
    abstracts = [r.get("abstract") for r in group if r.get("abstract")]
    out["abstract"] = max(abstracts, key=len) if abstracts else None
    out["source_ids"] = source_ids
    out["provenance"] = provenance
    out["sources"] = sorted(source_ids)
    out["id"] = stable_id(out)
    out["merged_from"] = len(group)
    return out


def stable_id(r: dict) -> str:
    """Prefer persistent identifiers so a record keeps its id across living updates."""

    doi = canonical_doi(r.get("doi"))
    if doi and not _ARXIV_DOI.match(doi):
        return f"doi:{doi}"
    if r.get("arxiv_id"):
        return f"arxiv:{r['arxiv_id']}"
    if r.get("pmid"):
        return f"pmid:{r['pmid']}"
    src, sid = next(iter(sorted((r.get("source_ids") or {"x": r.get("id", "?")}).items())))
    return f"{src}:{sid}"


def merge_records(records: Iterable[dict], *, title_threshold: float = 0.9) -> list[dict]:
    return [fold(g) for g in cluster(list(records), title_threshold=title_threshold)]


_CARRY = ("phase", "decisions", "extraction", "local_pdf_path", "checksum", "byte_count",
          "acquisition_status", "access_route", "failure_reason", "fulltext_txt_path")


def carry_over(new: list[dict], old: list[dict]) -> int:
    """Copy screening/acquisition state from a previous corpus onto matching new records."""

    index: dict[str, dict] = {}
    for r in old:
        for k in record_keys(r) + [f"id:{r['id']}"]:
            index[k] = r
    n = 0
    for r in new:
        prev = next((index[k] for k in record_keys(r) + [f"id:{r['id']}"] if k in index), None)
        if prev:
            for f in _CARRY:
                if f in prev:
                    r[f] = prev[f]
            n += 1
    return n
