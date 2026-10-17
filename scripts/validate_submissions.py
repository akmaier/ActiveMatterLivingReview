#!/usr/bin/env python3
"""Validate paper submissions (submissions/*.yml) in a pull request.

Runs in GitHub Actions with only PyYAML installed. For each file it checks the required fields,
the DOI format, that the DOI resolves at Crossref with a matching title, and whether the review
already knows the record (data/known_records.json, written by `amlr render`). It writes a Markdown
report to $GITHUB_STEP_SUMMARY (or stdout) and exits non-zero if any file is invalid.

A submission does not include a paper: after merge it enters the next update as a record
"identified via other methods" and is screened by the same panel as every database record.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("title", "year", "why")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
MAILTO = "andreas.maier@fau.de"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def crossref_title(doi: str) -> str | None:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    req = urllib.request.Request(url, headers={"User-Agent": f"amlr-submission-check (mailto:{MAILTO})"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            msg = json.load(r)["message"]
        return (msg.get("title") or [""])[0]
    except Exception:
        return None


def check(path: Path, known: dict) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return [f"not valid YAML: {e}"], notes
    if not isinstance(d, dict):
        return ["the file must be a YAML mapping (key: value lines)"], notes
    for f in REQUIRED:
        if not d.get(f):
            errors.append(f"missing `{f}`")
    doi = str(d.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
    arxiv = str(d.get("arxiv") or "").strip()
    if not doi and not arxiv:
        errors.append("give a `doi` or an `arxiv` id")
    if doi and not DOI.match(doi):
        errors.append(f"`doi` does not look like a DOI: {doi}")
    if arxiv and not ARXIV.match(arxiv):
        errors.append(f"`arxiv` should look like 2401.01234: {arxiv}")
    try:
        y = int(d.get("year"))
        if not 1950 <= y <= 2100:
            errors.append(f"`year` out of range: {y}")
    except (TypeError, ValueError):
        errors.append("`year` must be a number")
    if d.get("why") and len(str(d["why"]).split()) > 80:
        errors.append("`why` should be at most 80 words")
    if doi and DOI.match(doi):
        t = crossref_title(doi)
        if t is None:
            notes.append("Crossref did not return this DOI (fine for arXiv or very new papers).")
        else:
            sim = SequenceMatcher(None, norm(t), norm(d.get("title", ""))).ratio()
            if sim < 0.8:
                errors.append(f"title does not match Crossref ({sim:.2f}): \"{t}\"")
            else:
                notes.append(f"Crossref title matches ({sim:.2f}).")
    hit = known.get(doi) or known.get(f"arxiv:{arxiv}") or known.get("title:" + norm(d.get("title", "")))
    if hit:
        notes.append(f"already in the review as `{hit['id']}` (phase: {hit['phase']}); "
                     "merging adds the submission as a second source, it will not be screened twice.")
    return errors, notes


def main(paths: list[str]) -> int:
    kf = ROOT / "data" / "known_records.json"
    known = json.loads(kf.read_text(encoding="utf-8")) if kf.exists() else {}
    files = [Path(p) for p in paths] or sorted((ROOT / "submissions").glob("*.yml"))
    files = [f for f in files if f.suffix in (".yml", ".yaml") and f.name != "TEMPLATE.yml"]
    lines, bad = ["## Paper submissions", ""], 0
    for f in files:
        errors, notes = check(f, known)
        bad += bool(errors)
        lines.append(f"### {'❌' if errors else '✅'} `{f.name}`")
        lines += [f"- **error:** {e}" for e in errors] + [f"- {n}" for n in notes] + [""]
    if not files:
        lines.append("No submission files in this pull request.")
    report = "\n".join(lines)
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(report + "\n")
    print(report)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
