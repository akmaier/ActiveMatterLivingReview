"""Build data/corpus.jsonl from the latest per-source retrievals in data/raw/."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT
from .dedup import carry_over, merge_records
from .storage import locked, read_jsonl, rewrite_jsonl

RAW = REPO_ROOT / "data" / "raw"
CORPUS = REPO_ROOT / "data" / "corpus.jsonl"
MANIFEST = REPO_ROOT / "data" / "corpus_manifest.json"
# PRISMA 2020 reports these under "identification via other methods".
SUPPLEMENTARY = {"scholar", "citations", "handsearch"}
_FILE = re.compile(r"^(?P<src>[a-z_]+)-(?P<date>\d{4}-\d{2}-\d{2})\.jsonl$")


def latest_files(raw: Path = RAW) -> dict[str, Path]:
    latest: dict[str, tuple[str, Path]] = {}
    for p in raw.glob("*.jsonl"):
        m = _FILE.match(p.name)
        if m and (m["src"] not in latest or m["date"] > latest[m["src"]][0]):
            latest[m["src"]] = (m["date"], p)
    return {s: p for s, (_, p) in sorted(latest.items())}


def build(raw: Path = RAW, out: Path = CORPUS, manifest: Path = MANIFEST) -> dict:
    files = latest_files(raw)
    records, per_source = [], {}
    for src, p in files.items():
        rows = read_jsonl(p)
        per_source[src] = {"file": p.name, "records": len(rows)}
        records.extend(rows)
    merged = merge_records(records)
    with locked(out):
        carried = carry_over(merged, read_jsonl(out)) if out.exists() else 0
        rewrite_jsonl(out, merged)
    db = sum(v["records"] for s, v in per_source.items() if s not in SUPPLEMENTARY)
    other = sum(v["records"] for s, v in per_source.items() if s in SUPPLEMENTARY)
    info = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "per_source": per_source,
        "identified_db": db,
        "identified_other": other,
        "after_dedup": len(merged),
        "duplicates_removed": db + other - len(merged),
        "state_carried_over": carried,
    }
    manifest.write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info
