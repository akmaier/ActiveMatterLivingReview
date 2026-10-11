"""PRISMA 2020 counts + flow-diagram generator (pure-Python SVG, no Graphviz)."""

from __future__ import annotations

from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from typing import Iterable

from .schema import PrismaPhase as P


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
        duplicates = manifest["duplicates_removed"]
    else:
        identified_db, identified_other, duplicates = len(records), 0, n[P.duplicate.value]
    awaiting = n[P.identified.value]
    screened = in_corpus - awaiting
    excluded_screening = n[P.screened_out.value]

    reasons: Counter[str] = Counter()
    for r in records:
        if r.get("phase") == P.excluded_eligibility.value:
            decisions = r.get("decisions") or []
            reason = (decisions[-1].get("reason") if decisions else None) or "unspecified"
            reasons[reason] += 1

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
        "not_retrieved": n[P.fulltext_not_retrieved.value],
        "assessed": n[P.assessed.value] + n[P.excluded_eligibility.value] + n[P.included.value],
        "excluded_eligibility": n[P.excluded_eligibility.value],
        "excluded_eligibility_reasons": dict(reasons),
        "included_studies": n[P.included.value],
        "included_reports": n[P.included.value],
    }


_W, _BOX_W, _BOX_H, _ROW_H = 760, 300, 64, 104
_MAIN_X, _SIDE_X, _TOP = 110, 440, 20


def render_flow_svg(c: dict) -> str:
    """PRISMA 2020 flow (new-review template) as a standalone SVG string."""

    rows = [
        (
            "Identification",
            [f"Records identified from databases (n = {c['identified_db']})",
             f"Registers / hand-search (n = {c['identified_registers']})"],
            [f"Duplicates removed (n = {c['duplicates_removed']})"],
        ),
        (
            "Screening",
            [f"Records screened (n = {c['screened']})"],
            [f"Records excluded (n = {c['excluded_screening']})"],
        ),
        (
            "",
            [f"Reports sought for retrieval (n = {c['sought']})"],
            [f"Reports not retrieved (n = {c['not_retrieved']})"],
        ),
        (
            "",
            [f"Reports assessed for eligibility (n = {c['assessed']})"],
            [f"Reports excluded (n = {c['excluded_eligibility']})"]
            + [f"{k}: {v}" for k, v in sorted(c.get("excluded_eligibility_reasons", {}).items())][:3],
        ),
        (
            "Included",
            [f"Studies included in review (n = {c['included_studies']})",
             f"Reports of included studies (n = {c['included_reports']})"],
            None,
        ),
    ]
    height = _TOP * 2 + _ROW_H * len(rows)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {height}" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="12">',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#fff"/>',
    ]
    for i, (phase, main, side) in enumerate(rows):
        y = _TOP + i * _ROW_H
        if phase:
            out.append(
                f'<text x="40" y="{y + _BOX_H / 2}" transform="rotate(-90 40 {y + _BOX_H / 2})" '
                f'text-anchor="middle" font-weight="bold" fill="#1f4e79">{phase}</text>'
            )
        out.append(_box(_MAIN_X, y, main, fill="#eef4fb" if phase != "Included" else "#eef7ee"))
        if side:
            out.append(_box(_SIDE_X, y, side, fill="#f7f7f7"))
            out.append(_arrow(_MAIN_X + _BOX_W, y + _BOX_H / 2, _SIDE_X, y + _BOX_H / 2))
        if i < len(rows) - 1:
            cx = _MAIN_X + _BOX_W / 2
            out.append(_arrow(cx, y + _BOX_H, cx, y + _ROW_H))
    out.append(
        f'<text x="{_W - 10}" y="{height - 6}" text-anchor="end" font-size="10" fill="#666">'
        f'Snapshot {escape(str(c["snapshot_date"]))}</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def _box(x: float, y: float, lines: list[str], fill: str) -> str:
    step = 15
    y0 = y + _BOX_H / 2 - (len(lines) - 1) * step / 2 + 4
    text = "".join(
        f'<text x="{x + _BOX_W / 2}" y="{y0 + k * step}" text-anchor="middle">{escape(t, quote=False)}</text>'
        for k, t in enumerate(lines)
    )
    return (
        f'<rect x="{x}" y="{y}" width="{_BOX_W}" height="{_BOX_H}" rx="6" '
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
    """PRISMA 2020 flow as a TikZ picture for the manuscript (needs \\usetikzlibrary{positioning})."""

    reasons = "".join(
        f"\\\\ {_tex(k)}: {v}" for k, v in sorted(c.get("excluded_eligibility_reasons", {}).items())
    )
    return rf"""% Generated by `amlr prisma` (snapshot {c['snapshot_date']}). Do not edit.
\begin{{tikzpicture}}[node distance=4mm and 5mm, >=stealth, font=\scriptsize,
  box/.style={{draw, rounded corners, align=center, text width=38mm, minimum height=8mm,
    execute at begin node=\hyphenpenalty10000\relax}},
  side/.style={{box, text width=35mm, fill=gray!8}}]
\node[box] (id) {{Records identified from databases ($n={c['identified_db']}$)\\ registers / hand-search ($n={c['identified_registers']}$)}};
\node[side, right=of id] (dup) {{Duplicates removed ($n={c['duplicates_removed']}$)}};
\node[box, below=of id] (scr) {{Records screened ($n={c['screened']}$)}};
\node[side, right=of scr] (exs) {{Records excluded ($n={c['excluded_screening']}$)}};
\node[box, below=of scr] (sou) {{Reports sought for retrieval ($n={c['sought']}$)}};
\node[side, right=of sou] (nr) {{Reports not retrieved ($n={c['not_retrieved']}$)}};
\node[box, below=of sou] (ass) {{Reports assessed for eligibility ($n={c['assessed']}$)}};
\node[side, right=of ass] (exe) {{Reports excluded ($n={c['excluded_eligibility']}$){reasons}}};
\node[box, below=of ass, fill=green!6] (inc) {{Studies included ($n={c['included_studies']}$)\\ reports of included studies ($n={c['included_reports']}$)}};
\foreach \a/\b in {{id/scr, scr/sou, sou/ass, ass/inc}} \draw[->] (\a) -- (\b);
\foreach \a/\b in {{id/dup, scr/exs, sou/nr, ass/exe}} \draw[->] (\a) -- (\b);
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
