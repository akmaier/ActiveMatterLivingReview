"""CSV round-trip for human labelling (calibration and validation samples).

Screening itself is done by the LLM panel (`amlr.screen_llm`). Human labels for the pilot
and validation sets go out as an ASReview-compatible CSV and come back as `Decision`s.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from .schema import Decision, Stage


ASREVIEW_COLUMNS = ("record_id", "title", "abstract", "authors", "doi", "year")


def export_for_asreview(records: Iterable[dict], out_csv: Path) -> int:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ASREVIEW_COLUMNS)
        w.writeheader()
        for r in records:
            w.writerow(
                {
                    "record_id": r.get("id"),
                    "title": r.get("title", ""),
                    "abstract": r.get("abstract") or r.get("extraction", {}).get("abstract", ""),
                    "authors": "; ".join(r.get("authors", []) or []),
                    "doi": r.get("doi", "") or "",
                    "year": r.get("year", "") or "",
                }
            )
            n += 1
    return n


def import_decisions(
    labeled_csv: Path,
    reviewer: str,
    stage: Stage,
    at: date | None = None,
) -> list[tuple[str, Decision]]:
    """Parse ASReview-labeled CSV into (record_id, Decision) pairs.

    Does not open the corpus; the caller applies decisions to records.
    """

    at = at or date.today()
    pairs: list[tuple[str, Decision]] = []
    with labeled_csv.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            label = (row.get("included") or row.get("label") or "").strip().lower()
            if label in ("", "unlabeled"):
                continue
            include = label in ("1", "true", "yes", "include", "included")
            pairs.append(
                (
                    row["record_id"],
                    Decision(
                        reviewer=reviewer,
                        stage=stage,
                        include=include,
                        reason=row.get("note") or None,
                        at=at,
                    ),
                )
            )
    return pairs
