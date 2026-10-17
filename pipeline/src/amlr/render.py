"""Emit site data files and the paper's refs.bib from the corpus."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import date
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
            "platform": ((r.get("extraction") or {}).get("platform_class") or "").replace("_", " ") or None,
            "platform_name": (r.get("extraction") or {}).get("platform_name"),
            "agents": (r.get("extraction") or {}).get("n_agents_max"),
            "phenomena": ", ".join(p.replace("_", " ") for p in (r.get("extraction") or {}).get("phenomena") or []),
            "abstract_only": r.get("assessment_basis") == "abstract_only",
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
    included = [r for r in records if r.get("phase") == "included"]
    keys = bibkeys(included)
    with out.open("w", encoding="utf-8") as fh:
        for r in included:
            fh.write(_bibentry(r, keys[r["id"]]))
            fh.write("\n")
    return out


SNAPSHOT_FIELDS = ["platform_class", "platform_name", "n_agents_min", "n_agents_max", "agent_size_mm",
                   "propulsion", "interaction_modality", "control_architecture", "environment", "phenomena",
                   "observables", "theory_compared", "agreement", "n_independent_runs", "code_available",
                   "data_available", "rob.D1_replication", "rob.D2_agent_heterogeneity",
                   "rob.D3_finite_size_and_boundaries", "rob.D4_measurement_validity",
                   "rob.D5_data_code_availability", "rob.D6_quantitative_theory_comparison", "notes"]


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def write_snapshot(records: Iterable[dict], day: date | None = None) -> Path:
    """Dated, committed export of the included studies with their bib keys and extracted fields
    (`data/snapshots/<date>/included.csv`, plus a SHA-256 manifest)."""

    included = sorted((r for r in records if r.get("phase") == "included"), key=lambda r: r["id"])
    keys = bibkeys(included)
    snap = REPO_ROOT / "data" / "snapshots" / (day or date.today()).isoformat()
    snap.mkdir(parents=True, exist_ok=True)
    out = snap / "included.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "id", "doi", "year", "first_author", "title", "venue", "basis", *SNAPSHOT_FIELDS,
                    "unresolved", "text"])
        for r in included:
            e = r.get("extraction") or {}
            first = (r.get("authors") or [""])[0]
            w.writerow([keys[r["id"]], r["id"], r.get("doi") or "", r.get("year") or "", first,
                        r.get("title") or "", r.get("venue") or "",
                        "abstract" if r.get("assessment_basis") == "abstract_only" else "full_text",
                        *(_cell(e.get(f)) for f in SNAPSHOT_FIELDS), _cell(e.get("unresolved")),
                        r.get("fulltext_txt_path") or ""])
    manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(snap.iterdir())
                if p.is_file() and p.name != "MANIFEST.json"}
    (snap / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


_SAFE = re.compile(r"[^A-Za-z0-9]+")
_TAG = re.compile(r"<[^>]+>")
_TEX_SPECIAL = re.compile(r"([&%#_$])")


_SPACES = dict.fromkeys(map(ord, "\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f"), " ")
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2212"), "-")
_PUNCT = set("\u2013\u2014\u2018\u2019\u201c\u201d\u2026")


def _tex(s: str | None) -> str:
    """Plain metadata text made safe for a BibTeX field under pdfLaTeX: markup dropped, specials
    escaped, and characters pdfLaTeX's UTF-8 support lacks (e.g. CJK) left out."""

    s = unicodedata.normalize("NFC", _TAG.sub("", s or "")).translate(_SPACES).translate(_DASHES)
    s = "".join(ch for ch in s if ord(ch) < 0x180 or ch in _PUNCT)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return _TEX_SPECIAL.sub(r"\\\1", re.sub(r" {2,}", " ", s).strip())


def _name(a: str) -> str:
    """One BibTeX name. Metadata sometimes lists an institution as an author; braces keep its
    commas and its "and" from being parsed as name parts."""

    a = _tex(a)
    return f"{{{a}}}" if a.count(",") > 1 or " and " in a else a


def _bibentry(r: dict, key: str) -> str:
    year = r.get("year", "n.d.")
    authors = " and ".join(_name(a) for a in (r.get("authors", []) or ["Anonymous"]))
    title = _tex(r.get("title"))
    venue = _tex(r.get("venue"))
    # REVTeX's style prints the DOI as link text when an entry has no volume or pages.
    doi = _TEX_SPECIAL.sub(r"\\\1", r.get("doi") or "")
    return (
        f"@article{{{key},\n"
        f"  author = {{{authors}}},\n"
        f"  title  = {{{title}}},\n"
        f"  year   = {{{year}}},\n"
        f"  journal= {{{venue}}},\n"
        f"  doi    = {{{doi}}}\n"
        f"}}\n"
    )


def bibkeys(records: Iterable[dict]) -> dict[str, str]:
    """Stable, unique citation keys: author-year-title stem, with a/b/... on collisions."""

    stems: dict[str, list[str]] = {}
    for r in sorted(records, key=lambda r: r["id"]):
        stems.setdefault(_bibkey(r), []).append(r["id"])
    keys = {}
    for stem, ids in stems.items():
        for i, rid in enumerate(ids):
            keys[rid] = stem if len(ids) == 1 else f"{stem}{chr(97 + i)}"
    return keys


def _bibkey(r: dict) -> str:
    first = (r.get("authors") or ["anon"])[0]
    last = _SAFE.sub("", first.split(",")[0].split(" ")[-1]) or "anon"
    year = str(r.get("year") or "nd")
    title = _SAFE.sub("", (r.get("title") or "")[:20]).lower() or "untitled"
    return f"{last}{year}{title}"


# Facets of the reconfigurable taxonomy (/taxonomy/). Multi-label facets place a study under every
# label it carries, so counts at one level can sum to more than the parent.
TAXONOMY_FACETS = {
    "platform_class": ("Platform", False),
    "phenomena": ("Phenomenon", True),
    "theory_compared": ("Theory compared", True),
    "control_architecture": ("Control", False),
    "interaction_modality": ("Interaction", True),
    "propulsion": ("Propulsion", False),
    "agreement": ("Theory agreement", False),
    "scale": ("Collective size", False),
    "period": ("Period", False),
}


def _scale(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "not reported"
    return "2–9 agents" if n < 10 else "10–99 agents" if n < 100 else "100–999 agents" if n < 1000 else "≥ 1000 agents"


def _period(y) -> str:
    try:
        y = int(y)
    except (TypeError, ValueError):
        return "unknown"
    return "before 2010" if y < 2010 else "2010–2014" if y < 2015 else "2015–2019" if y < 2020 else "2020–2022" if y < 2023 else "2023–"


def write_taxonomy_json(records: Iterable[dict], out: Path | None = None) -> Path:
    out = out or (REPO_ROOT / "assets" / "taxonomy.json")
    included = sorted((r for r in records if r.get("phase") == "included"), key=lambda r: r["id"])
    keys = bibkeys(included)
    studies = []
    for r in included:
        e = r.get("extraction") or {}
        facets = {}
        for f, (_, multi) in TAXONOMY_FACETS.items():
            if f == "scale":
                v = _scale(e.get("n_agents_max"))
            elif f == "period":
                v = _period(r.get("year"))
            else:
                v = e.get(f)
            vals = (v or []) if multi else [v]
            vals = [str(x).replace("_", " ") for x in vals if x not in (None, "", "none")] or ["not reported"]
            facets[f] = vals
        studies.append({"key": keys[r["id"]], "title": r.get("title"), "year": r.get("year"),
                        "doi": r.get("doi"), "platform_name": e.get("platform_name"),
                        "n": e.get("n_agents_max"), "abstract_only": r.get("assessment_basis") == "abstract_only",
                        "f": facets})
    meta = {"facets": [{"id": f, "label": lab, "multi": multi} for f, (lab, multi) in TAXONOMY_FACETS.items()],
            "studies": studies, "snapshot": date.today().isoformat()}
    out.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out


def write_known_records(records: Iterable[dict], out: Path | None = None) -> Path:
    """DOI / arXiv / title index of every record the review holds (any phase), so the pull-request
    check can tell a submitter that a paper is already in the review."""

    out = out or (REPO_ROOT / "data" / "known_records.json")
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
    index: dict[str, dict] = {}
    for r in records:
        if r.get("phase") == "duplicate":
            continue
        entry = {"id": r["id"], "phase": r.get("phase")}
        for d in r.get("all_dois") or ([r["doi"]] if r.get("doi") else []):
            index[str(d).lower()] = entry
        if r.get("arxiv_id"):
            index[f"arxiv:{r['arxiv_id']}"] = entry
        if r.get("title"):
            index["title:" + norm(r["title"])] = entry
    out.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out


PLATFORM_LABELS = {
    "wheeled_or_legged_swarm_robots": "Wheeled or legged swarm robots",
    "other": "Other platforms",
    "robotic_micro_nano_agents": "Robotic micro- and nano-agents",
    "vibration_driven_robots": "Vibration-driven robots",
    "modular_or_self_reconfigurable_robots": "Modular or self-reconfigurable robots",
    "feedback_controlled_active_colloids": "Feedback-controlled active colloids",
    "smarticles_or_granular_robots": "Smarticles or granular robots",
    "robotic_metamaterial_or_active_solid": "Robotic metamaterials or active solids",
    "": "Not classified",
}


def write_platform_table(records: Iterable[dict], out: Path | None = None) -> Path:
    """Every included study by citation key, grouped by platform class (paper/tables/platform_index.tex).
    The caption text lives in paper/tables/platform_index_caption.tex, drafted with the prose."""

    out = out or (REPO_ROOT / "paper" / "tables" / "platform_index.tex")
    out.parent.mkdir(parents=True, exist_ok=True)
    included = [r for r in records if r.get("phase") == "included"]
    keys = bibkeys(included)
    groups: dict[str, list[str]] = {}
    for r in sorted(included, key=lambda r: (r.get("year") or 0, keys[r["id"]])):
        groups.setdefault((r.get("extraction") or {}).get("platform_class") or "", []).append(keys[r["id"]])
    order = sorted(groups, key=lambda g: (-len(groups[g]), g == ""))
    rows = [f"{PLATFORM_LABELS.get(g, g.replace('_', ' '))} & {len(groups[g])} & \\cite{{{','.join(groups[g])}}} \\\\"
            for g in order]
    body = "\n\\hline\n".join(rows)
    cap = out.with_name("platform_index_caption.tex")
    if not cap.exists():
        cap.write_text("% [CAPTION-DRAFT] to be drafted with the platforms section.\n", encoding="utf-8")
    # The caption text is embedded (an \\input inside \\caption breaks hyperref's bookmarks).
    caption = " ".join(l for l in cap.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("%")).strip()
    out.write_text(
        "% Generated by `amlr render` from the included-studies snapshot; do not edit by hand.\n"
        "\\begin{table*}[p]\n\\footnotesize\n"
        "\\caption{" + caption + "}\\label{tab:platform_index}\n"
        "\\begin{ruledtabular}\n\\begin{tabular}{p{0.2\\textwidth}rp{0.7\\textwidth}}\n"
        "Platform class & $N$ & Studies (by year) \\\\\n\\hline\n" + body + "\n"
        "\\end{tabular}\n\\end{ruledtabular}\n\\end{table*}\n", encoding="utf-8")
    return out
