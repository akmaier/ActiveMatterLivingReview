"""Client for the local Codex bridge (CodexCommandServer).

All manuscript prose is authored by Codex. This module only assembles the
prompt, sends it, and stores the reply verbatim under `paper/sections/`.
Every exchange is archived under `paper/drafts/` for provenance.
"""

from __future__ import annotations

import csv
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import REPO_ROOT

BRIDGE_URL = os.environ.get("CODEX_BRIDGE_URL", "http://127.0.0.1:8766")
# Mirrors MAX_REQUEST_BYTES in CodexCommandServer/server.py.
MAX_REQUEST_BYTES = 64 * 1024
# The bridge waits up to 600 s for Codex by default; give it headroom.
CLIENT_TIMEOUT_S = 900

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


def _evidence_block(budget_bytes: int) -> str:
    """Latest included-studies snapshot as CSV text, truncated to fit the byte budget."""

    snaps = sorted((REPO_ROOT / "data" / "snapshots").glob("*/included.csv"))
    if not snaps:
        return "(No included studies yet. Do not cite any specific study; use \\cite{TODO} placeholders.)"
    lines: list[str] = []
    used = 0
    with snaps[-1].open(encoding="utf-8") as fh:
        for row in csv.reader(fh):
            line = ",".join(row)
            if used + len(line.encode("utf-8")) + 1 > budget_bytes:
                lines.append("... (truncated)")
                break
            lines.append(line)
            used += len(line.encode("utf-8")) + 1
    return f"Snapshot: {snaps[-1].parent.name}\n" + "\n".join(lines)


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


def build_prompt(section: dict) -> str:
    style = (PAPER / "STYLE_WORDS.md").read_text(encoding="utf-8")
    protocol = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    fmt = _FORMAT_RULE[section.get("kind", "section")].format(**section)
    head = f"""You are the sole author of the prose for a PRISMA 2020 living systematic review on
robotic active matter, to be submitted to Reviews of Modern Physics (REVTeX 4.2).
RMP expects critical synthesis that identifies what works and sets directions, not a catalogue.

Write "{section['title']}" (id: {section['id']}), about {section['words']} words.
Scope: {section['brief']}

Hard rules:
- {fmt}
- Cite only with \\cite{{key}} using keys from the evidence table below. Never invent a reference;
  where a claim needs a source not in the table, write \\cite{{TODO}}.
- Make no factual claim about the literature that the evidence table does not support.
- Follow the voice guide below (didactic first-person plural, short sentences, varied openers).

=== VOICE GUIDE (STYLE_WORDS.md) ===
{style}

=== FROZEN PROTOCOL (for consistency of methods wording) ===
{protocol}

=== EVIDENCE TABLE (included studies) ===
"""
    used = len(head.encode("utf-8")) + 2048  # JSON envelope + escaping headroom
    return head + _evidence_block(MAX_REQUEST_BYTES - used)


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
    out.write_text(reply.strip() + "\n", encoding="utf-8")
    for issue in lint_style(reply):
        print(f"[style] {issue}")
    print(f"wrote {out}")
    return out
