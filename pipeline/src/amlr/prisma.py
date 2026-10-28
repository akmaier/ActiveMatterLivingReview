"""PRISMA 2020 counts + flow-diagram generator (pure-Python SVG, no Graphviz)."""

from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from typing import Iterable

from .schema import PrismaPhase as P


def _ao(records, phase: str) -> int:
    return sum(1 for r in records if r.get("phase") == phase and r.get("assessment_basis") == "abstract_only")


def compute_counts(records: Iterable[dict], today: date | None = None, manifest: dict | None = None) -> dict:
    """Identification / screening / eligibility / included counts for the flow diagram.

    `manifest` (from `amlr build-corpus`) supplies per-source identification counts and the
    number of duplicates removed; without it, duplicates are counted from `phase`.
    """

    records = list(records)
    n: Counter[str] = Counter(r.get("phase", P.identified.value) for r in records)
    in_corpus = len(records) - n[P.duplicate.value]
    if manifest:
        identified_db, identified_other = manifest["identified_db"], manifest["identified_other"]
        # Duplicates found after the corpus build (e.g. by link checks) are marked in place.
        duplicates = manifest["duplicates_removed"] + n[P.duplicate.value]
    else:
        identified_db, identified_other, duplicates = len(records), 0, n[P.duplicate.value]
    awaiting = n[P.identified.value]
    # Full text unobtainable but eligibility judged on the abstract (author decision): PRISMA
    # reports them as not retrieved, with the abstract-only assessment stated separately.
    abstract_only = sum(1 for r in records if r.get("assessment_basis") == "abstract_only"
                        and r.get("phase") in (P.assessed.value, P.included.value, P.excluded_eligibility.value))
    screened = in_corpus - awaiting
    excluded_screening = n[P.screened_out.value]

    reasons: Counter[str] = Counter()
    reasons_ft: Counter[str] = Counter()
    reasons_ao: Counter[str] = Counter()
    for r in records:
        if r.get("phase") == P.excluded_eligibility.value:
            # The latest full-text decision (panel, judge or author) carries the reason; a later
            # title/abstract label from the author's validation sample does not.
            decisions = [d for d in r.get("decisions") or [] if d.get("stage") == "full_text"] \
                or r.get("decisions") or []
            reason = (decisions[-1].get("reason") if decisions else None) or "unspecified"
            reasons[reason] += 1
            (reasons_ao if r.get("assessment_basis") == "abstract_only" else reasons_ft)[reason] += 1

    return {
        "snapshot_date": (today or date.today()).isoformat(),
        "identified_db": identified_db,
        "identified_registers": identified_other,
        "identified_by_source": {s: v["records"] for s, v in (manifest or {}).get("per_source", {}).items()},
        "duplicates_removed": duplicates,
        "awaiting_screening": awaiting,
        "screened": screened,
        "excluded_screening": excluded_screening,
        "sought": screened - excluded_screening,
        "not_retrieved": n[P.fulltext_not_retrieved.value] + abstract_only,
        "assessed_on_abstract_only": abstract_only,
        "abstract_only_included": sum(1 for r in records if r.get("assessment_basis") == "abstract_only"
                                      and r.get("phase") == P.included.value),
        "assessed": n[P.assessed.value] + n[P.excluded_eligibility.value] + n[P.included.value] - abstract_only,
        "excluded_eligibility": n[P.excluded_eligibility.value],
        # The same totals split by assessment basis, so the flow reconciles box by box:
        # assessed (full text) = included_full_text + excluded_full_text + awaiting_decision.
        "excluded_full_text": n[P.excluded_eligibility.value] - _ao(records, P.excluded_eligibility.value),
        "excluded_abstract_only": _ao(records, P.excluded_eligibility.value),
        "included_full_text": n[P.included.value] - _ao(records, P.included.value),
        "awaiting_decision": n[P.assessed.value],
        # Screened in, full text not yet sought to the end (living updates before tier-3 retrieval).
        "awaiting_retrieval": n[P.screened_in.value] + n[P.fulltext_sought.value],
        "excluded_eligibility_reasons": dict(sorted(reasons.items())),
        "excluded_full_text_reasons": dict(sorted(reasons_ft.items())),
        "excluded_abstract_only_reasons": dict(sorted(reasons_ao.items())),
        "included_studies": n[P.included.value],
        "included_reports": n[P.included.value],
    }


_COL_X = (110, 430, 750)  # main column, exclusions, abstract-only path
_BOX_W, _ROW_H, _TOP, _LINE = 290, 118, 20, 15


def _reason_lines(reasons: dict[str, int], per_line: int = 3) -> list[str]:
    items = [f"{k}: {v}" for k, v in sorted(reasons.items())]
    return ["  ·  ".join(items[i:i + per_line]) for i in range(0, len(items), per_line)]


def flow_boxes(c: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """The PRISMA 2020 flow as boxes (column, row, lines) and arrows between them.

    Every box reconciles with its neighbours: sought = not retrieved + assessed (full text);
    assessed = excluded (full text) + awaiting decision + included on full text; assessed on
    the abstract = excluded + included on the abstract; included = both included counts.
    """

    ao = c.get("assessed_on_abstract_only", 0)
    ft_reasons = c.get("excluded_full_text_reasons") or c.get("excluded_eligibility_reasons", {})
    included_lines = [f"Studies included in review (n = {c['included_studies']})",
                      f"Reports of included studies (n = {c['included_reports']})"]
    if ao:
        included_lines.append(f"on full text {c['included_full_text']}  ·  on abstract only "
                              f"{c['abstract_only_included']}")
    boxes = [
        dict(id="id", col=0, row=0, phase="Identification",
             lines=[f"Records identified from databases (n = {c['identified_db']})",
                    f"Registers / hand-search (n = {c['identified_registers']})"]),
        dict(id="dup", col=1, row=0, lines=[f"Duplicates removed (n = {c['duplicates_removed']})"]),
        dict(id="scr", col=0, row=1, phase="Screening", lines=[f"Records screened (n = {c['screened']})"]),
        dict(id="exs", col=1, row=1, lines=[f"Records excluded (n = {c['excluded_screening']})"]),
        dict(id="sou", col=0, row=2, lines=[f"Reports sought for retrieval (n = {c['sought']})"]),
        dict(id="nr", col=1, row=2, lines=[f"Reports not retrieved (n = {c['not_retrieved']})"]
             + ([f"of which assessed on abstract only (n = {ao})"] if ao else [])),
        dict(id="ass", col=0, row=3, lines=[f"Reports assessed for eligibility (n = {c['assessed']})"]),
        dict(id="exe", col=1, row=3,
             lines=[f"Reports excluded (n = {c.get('excluded_full_text', c['excluded_eligibility'])})"]
             + _reason_lines(ft_reasons)
             + ([f"Awaiting decision (n = {c['awaiting_decision']})"] if c.get("awaiting_decision") else [])),
        dict(id="inc", col=0, row=4, phase="Included", lines=included_lines, fill="#eef7ee"),
    ]
    arrows = [("id", "dup"), ("id", "scr"), ("scr", "exs"), ("scr", "sou"), ("sou", "nr"),
              ("sou", "ass"), ("ass", "exe"), ("ass", "inc")]
    if ao:
        boxes += [
            dict(id="aoa", col=2, row=2, lines=[f"Assessed on abstract only (n = {ao})"]),
            dict(id="aoe", col=2, row=3,
                 lines=[f"Excluded (n = {c['excluded_abstract_only']})"]
                 + _reason_lines(c.get("excluded_abstract_only_reasons", {}))
                 + [f"Included (n = {c['abstract_only_included']})"]),
        ]
        arrows += [("nr", "aoa"), ("aoa", "aoe"), ("aoe", "inc")]
    return boxes, arrows


def render_flow_svg(c: dict) -> str:
    """PRISMA 2020 flow (new-review template) as a standalone SVG string."""

    boxes, arrows = flow_boxes(c)
    ncols = 1 + max(b["col"] for b in boxes)
    width = _COL_X[ncols - 1] + _BOX_W + 20
    nrows = 1 + max(b["row"] for b in boxes)
    box_h = max(len(b["lines"]) for b in boxes) * _LINE + 16
    height = _TOP * 2 + _ROW_H * nrows
    geo = {b["id"]: (_COL_X[b["col"]], _TOP + b["row"] * _ROW_H) for b in boxes}
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="12">',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#fff"/>',
    ]
    for b in boxes:
        x, y = geo[b["id"]]
        if b.get("phase"):
            out.append(
                f'<text x="40" y="{y + box_h / 2}" transform="rotate(-90 40 {y + box_h / 2})" '
                f'text-anchor="middle" font-weight="bold" fill="#1f4e79">{b["phase"]}</text>'
            )
        fill = b.get("fill") or ("#eef4fb" if b["col"] == 0 else "#f7f7f7")
        out.append(_box(x, y, box_h, b["lines"], fill))
    for src, dst in arrows:
        (x1, y1), (x2, y2) = geo[src], geo[dst]
        if y1 == y2:  # same row: left box to right box
            out.append(_arrow(x1 + _BOX_W, y1 + box_h / 2, x2, y2 + box_h / 2))
        elif x1 == x2:  # same column: downwards
            out.append(_arrow(x1 + _BOX_W / 2, y1 + box_h, x2 + _BOX_W / 2, y2))
        else:  # back to the main column (abstract-only inclusions)
            out.append(_arrow(x1 + _BOX_W / 2, y1 + box_h, x2 + _BOX_W, y2 + box_h / 2))
    out.append(
        f'<text x="{width - 10}" y="{height - 6}" text-anchor="end" font-size="10" fill="#666">'
        f'Snapshot {escape(str(c["snapshot_date"]))}</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def _box(x: float, y: float, h: float, lines: list[str], fill: str) -> str:
    y0 = y + h / 2 - (len(lines) - 1) * _LINE / 2 + 4
    text = "".join(
        f'<text x="{x + _BOX_W / 2}" y="{y0 + k * _LINE}" text-anchor="middle">{escape(t, quote=False)}</text>'
        for k, t in enumerate(lines)
    )
    return (
        f'<rect x="{x}" y="{y}" width="{_BOX_W}" height="{h}" rx="6" '
        f'fill="{fill}" stroke="#333"/>{text}'
    )


def _arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#333" '
        f'stroke-width="1.2" marker-end="url(#a)"/>'
    )


_TEX_SPECIAL = {c: f"\\{c}" for c in "&%$#_{}"} | {"~": r"\textasciitilde{}", "^": r"\^{}", "\\": r"\textbackslash{}"}


def _tex(s: str) -> str:
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in s)


def render_flow_tikz(c: dict) -> str:
    """PRISMA 2020 flow as a TikZ picture for the manuscript (needs \\usetikzlibrary{positioning}).

    Same boxes and arrows as the SVG (`flow_boxes`)."""

    boxes, arrows = flow_boxes(c)
    grid = {(b["col"], b["row"]): b["id"] for b in boxes}
    nodes = []
    for b in sorted(boxes, key=lambda b: (b["row"], b["col"])):
        style = "box" if b["col"] == 0 else "side"
        if b["col"] == 0 and b["row"] == 0:
            place = ""
        elif b["col"] == 0:
            place = f", below=of {grid[(0, b['row'] - 1)]}"
        else:
            place = f", right=of {grid[(b['col'] - 1, b['row'])]}" if (b["col"] - 1, b["row"]) in grid \
                else f", below=of {grid[(b['col'], b['row'] - 1)]}"
        fill = ", fill=green!6" if b.get("fill") else ""
        text = r"\\ ".join(_tex(t) for t in b["lines"])
        nodes.append(rf"\node[{style}{place}{fill}] ({b['id']}) {{{text}}};")
    edges = " ".join(rf"\draw[->] ({a}) -- ({b});" for a, b in arrows)
    body = "\n".join(nodes)
    return rf"""% Generated by `amlr prisma` (snapshot {c['snapshot_date']}). Do not edit.
\begin{{tikzpicture}}[node distance=4mm and 5mm, >=stealth, font=\scriptsize,
  box/.style={{draw, rounded corners, align=center, text width=38mm, minimum height=8mm,
    execute at begin node=\hyphenpenalty10000\relax}},
  side/.style={{box, text width=35mm, fill=gray!8}}]
{body}
{edges}
\end{{tikzpicture}}
"""


def write_flow_tikz(counts: dict, out_tex: Path) -> Path:
    out_tex.parent.mkdir(parents=True, exist_ok=True)
    out_tex.write_text(render_flow_tikz(counts), encoding="utf-8")
    return out_tex


def write_flow_svg(counts: dict, out_svg: Path) -> Path:
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(render_flow_svg(counts), encoding="utf-8")
    return out_svg
