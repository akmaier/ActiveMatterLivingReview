"""Client for the local Codex bridge (`amlr.codex_bridge`, started with `amlr bridge`).

All manuscript prose is authored by Codex. This module only assembles the
prompt, sends it, and stores the reply verbatim under `paper/sections/`.
Every exchange is archived under `paper/drafts/` for provenance.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .codex_bridge import MAX_REQUEST_BYTES  # the bridge rejects larger bodies
from .config import REPO_ROOT

BRIDGE_URL = os.environ.get("CODEX_BRIDGE_URL", "http://127.0.0.1:8766")
# `amlr bridge` gives up a turn after 3000 s by default; wait a little longer than it does.
CLIENT_TIMEOUT_S = 3300

PAPER = REPO_ROOT / "paper"


class BridgeError(RuntimeError):
    pass


def health() -> bool:
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/health", timeout=5) as r:
            return json.load(r).get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def query(message: str) -> str:
    body = json.dumps({"message": message}, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        raise BridgeError(
            f"prompt is {len(body)} bytes; the bridge accepts at most {MAX_REQUEST_BYTES}"
        )
    headers = {"content-type": "application/json"}
    token = os.environ.get("CODEX_BRIDGE_TOKEN")
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BRIDGE_URL}/v1/query", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=CLIENT_TIMEOUT_S) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        raise BridgeError(f"bridge returned {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    reply = payload.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise BridgeError(f"bridge returned no reply: {payload}")
    return reply


def load_sections() -> list[dict]:
    with (PAPER / "sections.yml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["sections"]


def _snapshot() -> Path | None:
    snaps = sorted((REPO_ROOT / "data" / "snapshots").glob("*/included.csv"))
    return snaps[-1] if snaps else None


_FORMAT_RULE = {
    "section": "Output only the LaTeX of this section, beginning with "
    "\\section{{{title}}}\\label{{sec:{id}}}. No preamble, no \\begin{{document}}.",
    "plain": "Output only LaTeX paragraphs: no sectioning commands, no preamble, no environments "
    "around the whole text.",
    "body": "Output the LaTeX body of a standalone document (\\section commands allowed), with no "
    "preamble and no \\begin{{document}}.",
}


def output_path(section: dict) -> Path:
    return REPO_ROOT / section["out"] if "out" in section else PAPER / "sections" / f"{section['id']}.tex"


def _drafted(exclude: str) -> list[Path]:
    out = []
    for spec in load_sections():
        path = output_path(spec)
        if spec["id"] != exclude and path.exists() and "[CODEX-DRAFT] not drafted yet" not in path.read_text(encoding="utf-8"):
            out.append(path)
    return out


def build_prompt(section: dict) -> str:
    """The prompt names the evidence files instead of inlining them: Codex reads them itself
    (read-only sandbox), so the bridge's 64 KB request limit never truncates the evidence."""

    style = (PAPER / "STYLE_WORDS.md").read_text(encoding="utf-8")
    fmt = _FORMAT_RULE[section.get("kind", "section")].format(**section)
    snap = _snapshot()
    if snap is None:
        raise BridgeError("no data/snapshots/*/included.csv yet; run `amlr render` first")
    prisma = snap.parent / "prisma_counts.json"
    drafted = "\n".join(f"  - {p}" for p in _drafted(section["id"])) or "  (none yet)"
    return f"""You are the sole author of the prose for a PRISMA 2020 living systematic review on
robotic active matter, to be submitted to Reviews of Modern Physics (REVTeX 4.2).
RMP expects critical synthesis that identifies what works and sets directions, not a catalogue.

Write "{section['title']}" (id: {section['id']}), about {section['words']} words.
Scope: {section['brief']}

Before writing, read these files with read-only shell commands. Do not create or modify any file;
return the text in your reply.
- Evidence table, one row per included study (snapshot {snap.parent.name}): {snap}
  `key` is the citation key in {PAPER / 'refs.bib'}. The other columns hold the data items the
  panel extracted and reconciled; the vocabularies are defined in {REPO_ROOT / 'protocol' / 'extraction_prompt.md'}.
  `basis=abstract` marks studies assessed on the abstract only. `unresolved` lists fields still
  awaiting the author's check. `text` is the study's extracted full text, relative to {REPO_ROOT}.
- PRISMA counts for the same snapshot: {prisma}
- Frozen protocol: {REPO_ROOT / 'protocol' / 'PROTOCOL.md'}; eligibility criteria: {REPO_ROOT / 'protocol' / 'PICO.md'}
- Validation and adjudication: rater agreement on the 200-record sample in the newest
  {REPO_ROOT / 'data' / 'human_check'}/agreement-*.json (keys final:<rater> and blind:<rater>);
  the Opus judge's instructions, decisions and flags in {REPO_ROOT / 'data' / 'conflicts' / 'judge'}/
  (INSTRUCTIONS.md, decisions-*.jsonl, FLAGS.md); the amendment log at the end of PROTOCOL.md.
- Figures you may place (files, labels, owner sections): {PAPER / 'figures' / 'FIGURES.md'}
- Manuscript plan, with every section's brief (avoid overlap): {PAPER / 'sections.yml'}
- Other sections (keep terminology consistent; where their numbers differ from the current
  snapshot, the snapshot wins, because those drafts may predate it):
{drafted}

This is a full redraft for the current snapshot. Earlier drafts may cite studies that are no
longer included or counts that have changed; rewrite rather than patch.

Hard rules:
- {fmt}
- Cite included studies only with \\cite{{key}}, using keys from the `key` column. Never invent a
  key. Where a claim needs a source outside the table (a theory paper, an earlier review), write
  \\todocite{{short description}} instead.
- Compute every count, share or trend you report about the evidence base from the evidence table
  or the PRISMA counts (you may run read-only scripts), and name the snapshot date once.
- Claim nothing about a study that its row or its full text does not support. Check specific
  numbers against the full text before stating them. Quote at most a few words from any paper.
- Where a point rests on studies assessed on the abstract only, or on fields still unresolved,
  say so.
- Cite broadly: every study that supports a statement belongs in its \\cite list, and the
  synthesis sections together should cite most of the included studies, not a few exemplars.
- Typeset for a two-column REVTeX page without overfull lines: no long unbreakable tokens in
  running text (wrap file paths or identifiers in \\path{{...}}, avoid \\texttt for long strings),
  tables with p{{}} columns sized to fit \\columnwidth or, in table*, \\textwidth. Boolean search
  strings never go inline or in \\textsc: set them as a displayed block
  (\\begin{{quote}}\\raggedright\\small ... \\end{{quote}}) in lower case, with spaces around operators.
- Facts the files do not contain (author biography, funding, affiliations of others) go in as
  [placeholders]; never make them up.
- Follow the voice guide below (didactic first-person plural, short sentences, varied openers).

=== VOICE GUIDE (STYLE_WORDS.md) ===
{style}
"""


_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.S)


def _unfence(reply: str) -> str:
    """Drop a Markdown code fence around the whole reply (mechanical; the prose is untouched)."""

    m = _FENCE.match(reply.strip())
    return (m.group(1) if m else reply).strip()


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\])")


def lint_style(tex: str) -> list[str]:
    """Flag three or more consecutive sentences sharing an opener (STYLE_WORDS 'Variety' rule)."""

    text = re.sub(r"%.*", "", tex)
    sentences = [s.strip() for s in _SENT.split(text) if s.strip()]
    openers = [s.split()[0].strip(",").lower() for s in sentences if s.split()]
    issues = []
    for i in range(2, len(openers)):
        if openers[i] == openers[i - 1] == openers[i - 2]:
            issues.append(f"three consecutive sentences open with '{openers[i]}': {sentences[i][:60]}...")
    return issues


def draft_section(section: str, dry_run: bool = False) -> Path | None:
    spec = next((s for s in load_sections() if s["id"] == section), None)
    if spec is None:
        raise SystemExit(f"unknown section '{section}'; see paper/sections.yml")
    prompt = build_prompt(spec)
    if dry_run:
        print(prompt)
        print(f"\n[dry-run] {len(prompt.encode('utf-8'))} bytes; limit {MAX_REQUEST_BYTES}")
        return None
    if not health():
        raise BridgeError(f"Codex bridge not reachable at {BRIDGE_URL}")
    reply = query(prompt)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    drafts = PAPER / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / f"{section}-{stamp}.json").write_text(
        json.dumps({"section": section, "prompt": prompt, "reply": reply}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out = output_path(spec)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_unfence(reply) + "\n", encoding="utf-8")
    for issue in lint_style(reply):
        print(f"[style] {issue}")
    print(f"wrote {out}")
    return out
