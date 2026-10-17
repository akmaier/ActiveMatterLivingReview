"""Manuscript figures generated from the latest included-studies snapshot (`amlr figures`).

Every figure is a vector PDF in `paper/figures/` and is regenerated on each living update, so the
numbers in the figures always match `data/snapshots/<date>/included.csv`.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .config import REPO_ROOT  # noqa: E402

OUT = REPO_ROOT / "paper" / "figures"
COL, FULL = 3.375, 7.0  # REVTeX column and page widths (inches)
PALETTE = ["#3366cc", "#dc7633", "#239b56", "#c0392b", "#7d3c98", "#a04000", "#d4ac0d", "#2e86c1",
           "#1abc9c", "#7b7d7d"]

plt.rcParams.update({
    "font.family": "serif", "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7, "axes.spines.top": False,
    "axes.spines.right": False, "axes.linewidth": 0.6, "pdf.fonttype": 42,
})


def _snapshot() -> Path:
    return sorted((REPO_ROOT / "data" / "snapshots").glob("*/included.csv"))[-1]


def _rows() -> list[dict]:
    with _snapshot().open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _labels(v: str) -> list[str]:
    out = [x.strip().replace("_", " ") for x in (v or "").split(";") if x.strip() and x.strip() != "none"]
    return out or ["not reported"]


def _pretty(s: str) -> str:
    return {"wheeled or legged swarm robots": "wheeled/legged swarms", "robotic micro nano agents": "micro/nano robots",
            "vibration driven robots": "vibration-driven", "modular or self reconfigurable robots": "modular/reconfigurable",
            "feedback controlled active colloids": "feedback colloids", "robotic metamaterial or active solid": "metamaterials/active solids",
            "smarticles or granular robots": "smarticles/granular", "self assembly or shape formation": "self-assembly/shape",
            "transport or locomotion": "transport/locomotion", "flocking polar order": "flocking/polar order",
            "clustering or mips": "clustering/MIPS", "chirality or rotation": "chirality/rotation",
            "swarming or vortex": "swarming/vortex", "boundary accumulation": "boundary accumulation",
            "jamming or crystallization": "jamming/crystallization", "active solid or odd elasticity": "active solid/odd elasticity",
            "agent based simulation": "agent-based simulation", "active brownian particles": "active Brownian particles",
            "kinetic or hydrodynamic theory": "kinetic/hydrodynamic", "statistical mechanics other": "other stat. mech.",
            "vicsek type": "Vicsek-type", "run and tumble": "run-and-tumble", "active elasticity": "active elasticity",
            "no control passive rules": "passive rules", "onboard rules": "onboard rules", "external feedback": "external feedback",
            "learned policy": "learned policy", "central controller": "central controller",
            "optical or sensing": "optical/sensing", "programmed rules": "programmed rules",
            "environment mediated": "environment-mediated", "steric contact": "steric contact"}.get(s, s)


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.pdf"
    fig.savefig(path, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return path


def taxonomy_overview(rows: list[dict]) -> Path:
    """Platform class x phenomenon: counts of studies (multi-label phenomena), with marginals."""

    plats = Counter(_pretty(r["platform_class"].replace("_", " ") or "not reported") for r in rows)
    phen = Counter(_pretty(p) for r in rows for p in _labels(r["phenomena"]))
    P = [p for p, _ in plats.most_common()]
    F = [f for f, _ in phen.most_common() if f != "not reported"]
    M = np.zeros((len(F), len(P)), dtype=int)
    for r in rows:
        pi = P.index(_pretty(r["platform_class"].replace("_", " ") or "not reported"))
        for f in {_pretty(x) for x in _labels(r["phenomena"])}:
            if f in F:
                M[F.index(f), pi] += 1
    fig = plt.figure(figsize=(FULL, 3.9))
    gs = fig.add_gridspec(2, 2, width_ratios=[5, 1.1], height_ratios=[1.0, 4], wspace=0.04, hspace=0.05)
    ax = fig.add_subplot(gs[1, 0])
    im = ax.imshow(M, aspect="auto", cmap="Blues")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if M[i, j]:
                ax.text(j, i, M[i, j], ha="center", va="center", fontsize=6.5,
                        color="white" if M[i, j] > M.max() * 0.55 else "#1f2328")
    ax.set_xticks(range(len(P)), P, rotation=35, ha="right")
    ax.set_yticks(range(len(F)), F)
    ax.set_xlabel("Platform class")
    ax.spines[:].set_visible(False)
    top = fig.add_subplot(gs[0, 0], sharex=ax)
    top.bar(range(len(P)), [plats[p] for p in P], color="#3366cc")
    top.set_ylabel("studies")
    top.tick_params(labelbottom=False)
    right = fig.add_subplot(gs[1, 1], sharey=ax)
    right.barh(range(len(F)), [phen[f] for f in F], color="#239b56")
    right.set_xlabel("studies")
    right.tick_params(labelleft=False)
    fig.colorbar(im, ax=right, fraction=0.25, pad=0.12, label="studies in cell")
    return _save(fig, "taxonomy_overview")


def _stacked(ax, rows, outer: str, inner: str, outer_order=None, inner_order=None, multi_outer=False):
    pairs = Counter()
    for r in rows:
        os_ = [_pretty(x) for x in (_labels(r[outer]) if multi_outer else [r[outer].replace("_", " ") or "not reported"])]
        for o in set(os_):
            pairs[(o, _pretty(r[inner].replace("_", " ") or "not reported"))] += 1
    tot_o, tot_i = Counter(), Counter()
    for (o, i), n in pairs.items():
        tot_o[o] += n
        tot_i[i] += n
    O = outer_order or [o for o, _ in tot_o.most_common()]
    I = [i for i in inner_order if tot_i[i]] if inner_order else [i for i, _ in tot_i.most_common()]
    left = np.zeros(len(O))
    for k, i in enumerate(I):
        vals = np.array([pairs[(o, i)] for o in O])
        ax.barh(range(len(O)), vals, left=left, color=PALETTE[k % len(PALETTE)], label=i, height=0.7)
        left += vals
    ax.set_yticks(range(len(O)), O)
    ax.invert_yaxis()
    ax.set_xlabel("studies")
    return O, I


def theory_agreement(rows: list[dict]) -> Path:
    """Sub-taxonomy: theory compared, split by how the comparison was made."""

    fig, ax = plt.subplots(figsize=(COL, 2.6))
    _stacked(ax, rows, "theory_compared", "agreement", multi_outer=True,
             inner_order=["quantitative", "qualitative", "none", "not reported"])
    ax.legend(title="agreement", frameon=False, loc="lower right")
    return _save(fig, "subtaxonomy_theory")


def control_scale(rows: list[dict]) -> Path:
    """Sub-taxonomy: control architecture, split by the largest collective in hardware."""

    def scale(n):
        try:
            n = int(float(n))
        except ValueError:
            return "not reported"
        return "2–9" if n < 10 else "10–99" if n < 100 else "100–999" if n < 1000 else "≥1000"

    rows2 = [{**r, "scale": scale(r["n_agents_max"])} for r in rows]
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    _stacked(ax, rows2, "control_architecture", "scale",
             inner_order=["2–9", "10–99", "100–999", "≥1000", "not reported"])
    ax.legend(title="agents (max)", frameon=False, loc="lower right")
    return _save(fig, "subtaxonomy_control")


def interaction_platform(rows: list[dict]) -> Path:
    """Sub-taxonomy: interaction modality, split by platform class."""

    fig, ax = plt.subplots(figsize=(FULL, 2.4))
    _stacked(ax, rows, "interaction_modality", "platform_class", multi_outer=True)
    ax.legend(title="platform class", frameon=False, ncol=2, loc="lower right")
    return _save(fig, "subtaxonomy_interaction")


def growth(rows: list[dict]) -> Path:
    """Included studies per year, stacked by platform class."""

    years = sorted({int(r["year"]) for r in rows if r["year"]})
    plats = [p for p, _ in Counter(_pretty(r["platform_class"].replace("_", " ")) for r in rows).most_common()]
    ys = np.arange(years[0], years[-1] + 1)
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    bottom = np.zeros(len(ys))
    for k, p in enumerate(plats):
        v = np.array([sum(1 for r in rows if r["year"] and int(r["year"]) == y and _pretty(r["platform_class"].replace("_", " ")) == p) for y in ys])
        ax.bar(ys, v, bottom=bottom, color=PALETTE[k % len(PALETTE)], width=0.85, label=p)
        bottom += v
    ax.set_xlabel("publication year")
    ax.set_ylabel("included studies")
    ax.legend(frameon=False, fontsize=5.8, loc="upper left")
    return _save(fig, "growth")


def agreement() -> Path | None:
    """Raters against the author's final labels on the 200-record validation sample."""

    files = sorted((REPO_ROOT / "data" / "human_check").glob("agreement-*.json"))
    if not files:
        return None
    a = json.loads(files[-1].read_text())
    raters = [("panel", "panel (R1–R3)"), ("R1", "R1 gpt-oss-120b"), ("R2", "R2 Magistral"), ("opus", "Claude Opus")]
    raters = [(k, lab) for k, lab in raters if f"final:{k}" in a]
    metrics = [("sens", "sensitivity"), ("spec", "specificity"), ("kappa", "Cohen's κ")]
    fig, ax = plt.subplots(figsize=(COL, 2.0))
    w = 0.8 / len(raters)
    for i, (k, lab) in enumerate(raters):
        vals = [a[f"final:{k}"][m] for m, _ in metrics]
        ax.bar(np.arange(len(metrics)) + (i - (len(raters) - 1) / 2) * w, vals, w, color=PALETTE[i], label=lab)
    ax.set_xticks(range(len(metrics)), [m for _, m in metrics])
    ax.set_ylim(0, 1.05)
    ax.axhline(0.95, color="#7b7d7d", lw=0.6, ls="--")
    ax.legend(frameon=False, fontsize=6, loc="lower left")
    return _save(fig, "validation_agreement")


def make_all() -> list[Path]:
    rows = _rows()
    out = [taxonomy_overview(rows), theory_agreement(rows), control_scale(rows), interaction_platform(rows), growth(rows)]
    if (p := agreement()) is not None:
        out.append(p)
    return out
