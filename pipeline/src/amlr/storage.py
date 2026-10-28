"""Corpus storage.

Line-delimited JSON is the canonical corpus
store and add Parquet/CSV *exports* for the dated snapshots that get
committed under `data/snapshots/`.
"""

from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    pa = None
    pq = None


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Exclusive advisory lock on `<path>.lock`, so concurrent pipeline steps serialize their
    read-modify-write of the same corpus file instead of overwriting each other."""

    import fcntl

    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def rewrite_jsonl(path: Path, rows: Iterable[dict]) -> None:
    """Atomic replace (write temp file, then rename)."""

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    """Append rows to a JSONL file; returns the number written."""

    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list; empty list if the file is absent."""

    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def snapshot_dir(root: Path, today: date | None = None) -> Path:
    """Return (and create) the snapshot directory for a given date."""

    today = today or date.today()
    out = root / today.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    return out


def export_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: _flatten(r.get(k)) for k in fieldnames})


def export_parquet(path: Path, rows: list[dict]) -> None:
    if pa is None or pq is None:  # pragma: no cover
        raise RuntimeError("pyarrow is required for Parquet export")
    if not rows:
        path.touch()
        return
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def _flatten(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return v
