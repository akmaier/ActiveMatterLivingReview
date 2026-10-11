"""Emit site data files and the paper's refs.bib from the corpus."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import yaml

from .config import REPO_ROOT


def write_corpus_yml(records: Iterable[dict], out: Path | None = None) -> Path:
    out = out or (REPO_ROOT / "_data" / "corpus.yml")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": r.get("id"),
            "year": r.get("year"),
            "title": r.get("title"),
            "authors": "; ".join(r.get("authors", []) or []),
            "venue": r.get("venue"),
            "platform": (r.get("extraction") or {}).get("platform"),
            "agents": (r.get("extraction") or {}).get("agents"),
            "doi": r.get("doi"),
        }
        for r in records
        if r.get("phase") == "included"
    ]
    with out.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(rows, fh, sort_keys=False, allow_unicode=True)
    return out


def write_bibtex(records: Iterable[dict], out: Path | None = None) -> Path:
    out = out or (REPO_ROOT / "paper" / "refs.bib")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in records:
            if r.get("phase") != "included":
                continue
            fh.write(_bibentry(r))
            fh.write("\n")
    return out


_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _bibentry(r: dict) -> str:
    key = _bibkey(r)
    year = r.get("year", "n.d.")
    authors = " and ".join(r.get("authors", []) or ["Anonymous"])
    title = (r.get("title") or "").replace("{", "").replace("}", "")
    venue = r.get("venue") or ""
    doi = r.get("doi") or ""
    return (
        f"@article{{{key},\n"
        f"  author = {{{authors}}},\n"
        f"  title  = {{{title}}},\n"
        f"  year   = {{{year}}},\n"
        f"  journal= {{{venue}}},\n"
        f"  doi    = {{{doi}}}\n"
        f"}}\n"
    )


def _bibkey(r: dict) -> str:
    first = (r.get("authors") or ["anon"])[0]
    last = _SAFE.sub("", first.split(",")[0].split(" ")[-1]) or "anon"
    year = str(r.get("year") or "nd")
    title = _SAFE.sub("", (r.get("title") or "")[:20]).lower() or "untitled"
    return f"{last}{year}{title}"
