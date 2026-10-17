"""Author validation and adjudication (PROTOCOL §6 "Validation", §7 unresolved fields).

`build_queue` writes the click-through queue served at /check/ on the site. The page keeps the
author's labels in the browser and exports them as JSON; `import_labels` appends that export to
the ledger `data/human_check/labels.jsonl` and `apply` writes the latest label per item into the
corpus. Rules for applying them:

- Title/abstract sample: an author include sends a panel-excluded record to full-text retrieval.
  An author exclude of a record the panel passed is reported, not applied, because the full-text
  assessment supersedes the title/abstract decision.
- Full-text splits and seed papers: the author decision replaces the panel decision.
- Extraction: the chosen value replaces an unresolved field and survives re-extraction.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from .config import REPO_ROOT
from .extract import CODED, COUNTS, LEDGER as EXTRACTION_LEDGER, SIZES, field_values, load_prompt
from .schema import Decision, PrismaPhase, Stage
from .storage import locked, read_jsonl, rewrite_jsonl, write_jsonl

DIR = REPO_ROOT / "data" / "human_check"
LABELS = DIR / "labels.jsonl"
TA_SAMPLE = DIR / "ta_sample.txt"
QUEUE = REPO_ROOT / "assets" / "human_check.json"
SEEDS = REPO_ROOT / "protocol" / "search_strategies" / "seed_set.yml"
FORMAT = "amlr-human-check/1"
TA_SAMPLE_SIZE = 200
TA_SALT = "amlr-ta-validation-v1:"
REVIEWER = "author"
JUDGE = "judge:opus"  # LLM judge the author delegated the remaining conflicts to (amendment 6)

VOCAB = {
    "platform_class": ["vibration_driven_robots", "wheeled_or_legged_swarm_robots",
                       "modular_or_self_reconfigurable_robots", "smarticles_or_granular_robots",
                       "robotic_micro_nano_agents", "feedback_controlled_active_colloids",
                       "robotic_metamaterial_or_active_solid", "other"],
    "propulsion": ["vibration", "wheels", "legs", "magnetic_field", "light", "acoustic", "chemical", "other"],
    "control_architecture": ["no_control_passive_rules", "onboard_rules", "external_feedback",
                             "learned_policy", "central_controller", "other"],
    "agreement": ["quantitative", "qualitative", "none"],
    "code_available": [True, False],
    "data_available": [True, False],
}
ROB_LEVELS = ["low", "some_concerns", "high"]
FIELD_DEFS = {
    "platform_class": "platform class, one of " + ", ".join(VOCAB["platform_class"]),
    "propulsion": "propulsion, one of " + ", ".join(VOCAB["propulsion"]),
    "control_architecture": "control architecture, one of " + ", ".join(VOCAB["control_architecture"]),
    "agreement": "how theory and experiment were compared: quantitative, qualitative or none",
    "n_agents_min": "smallest number of agents used in hardware experiments (integer)",
    "n_agents_max": "largest number of agents used in hardware experiments (integer)",
    "n_independent_runs": "number of independent experimental repetitions reported (integer)",
    "agent_size_mm": "characteristic agent size in millimetres",
    "code_available": "true only if a code repository or archive is named",
    "data_available": "true only if a data repository or archive is named",
    **{f"rob.{d}": f"risk of bias, domain {d}: low, some_concerns or high"
       for d in ("D1_replication", "D2_agent_heterogeneity", "D3_finite_size_and_boundaries",
                 "D4_measurement_validity", "D5_data_code_availability", "D6_quantitative_theory_comparison")},
}


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _authors(r: dict) -> str:
    a = r.get("authors") or []
    return "; ".join(a[:3]) + (" et al." if len(a) > 3 else "")


def _link(r: dict) -> str | None:
    if r.get("doi"):
        return f"https://doi.org/{r['doi']}"
    if r.get("arxiv_id"):
        return f"https://arxiv.org/abs/{r['arxiv_id']}"
    return None


def _votes(r: dict, stage: str) -> dict | None:
    ds = [d for d in r.get("decisions") or [] if d.get("stage") == stage]
    panel = next((d for d in reversed(ds) if d.get("reviewer") == "panel"), None)
    if panel is None:
        return None
    return {
        "include": panel.get("include"), "reason": panel.get("reason"), "votes": panel.get("votes"),
        "reviewers": [{"r": d["reviewer"], "model": d.get("model"), "include": d.get("include"),
                       "reason": d.get("reason"), "confidence": d.get("confidence"),
                       "rationale": d.get("rationale")}
                      for d in ds if d.get("reviewer") not in ("panel", REVIEWER, JUDGE)],
    }


def _item(r: dict) -> dict:
    return {"id": r["id"], "title": r.get("title"), "authors": _authors(r), "year": r.get("year"),
            "venue": r.get("venue"), "link": _link(r), "abstract": r.get("abstract"),
            "phase": r.get("phase"), "abstract_only": r.get("assessment_basis") == "abstract_only"}


def ta_sample(records: list[dict]) -> list[str]:
    """The fixed random sample of title/abstract decisions (frozen in ta_sample.txt once drawn)."""

    if TA_SAMPLE.exists():
        return [x for x in TA_SAMPLE.read_text(encoding="utf-8").split() if x]
    pool = [r["id"] for r in records if _votes(r, Stage.title_abstract.value)]
    ids = sorted(pool, key=lambda i: hashlib.sha256((TA_SALT + i).encode()).hexdigest())[:TA_SAMPLE_SIZE]
    TA_SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    TA_SAMPLE.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return ids


def _is_split(r: dict) -> bool:
    v = _votes(r, Stage.full_text.value)
    return bool(v) and v["votes"] in ("1/3", "2/3")


def _extraction_votes() -> dict[str, dict[str, dict]]:
    _, _, sha = load_prompt()
    out: dict[str, dict[str, dict]] = {}
    for v in read_jsonl(EXTRACTION_LEDGER):
        if v.get("prompt_sha256") == sha and v.get("data") is not None:
            out.setdefault(v["record_id"], {})[v["reviewer"]] = v["data"]
    return out


def _field_kind(f: str) -> str:
    if f.startswith("rob."):
        return "rob"
    if f in COUNTS:
        return "count"
    if f in SIZES:
        return "size"
    return "coded" if f in CODED else "other"


def _seed_ids(records: list[dict]) -> list[str]:
    seeds = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))["seed"]
    by_doi = {(r.get("doi") or "").lower(): r["id"] for r in records if r.get("doi")}
    by_title = {_norm_title(r.get("title")): r["id"] for r in records if r.get("title")}
    out = []
    for s in seeds:
        rid = by_doi.get((s.get("doi") or "").lower()) or by_title.get(_norm_title(s["title"]))
        if rid and rid not in out:
            out.append(rid)
    return out


def build_queue(corpus: Path, out: Path = QUEUE) -> dict:
    records = read_jsonl(corpus)
    by_id = {r["id"]: r for r in records}
    for r in records:
        for alias in r.get("previous_ids") or []:
            by_id.setdefault(alias, r)

    ta = []
    for rid in ta_sample(records):
        r = by_id.get(rid)
        if r is not None:
            ta.append({**_item(r), "panel": _votes(r, Stage.title_abstract.value)})

    # Panel includes first: an error there changes the synthesis, an error in an exclude does not.
    splits = sorted((r for r in records if _is_split(r)),
                    key=lambda r: (not _votes(r, Stage.full_text.value)["include"], -(r.get("year") or 0)))
    from .evidence import latest as latest_evidence, recheck
    from .fulltext.dispatch import text_for

    ev = latest_evidence()
    texts: dict[str, str] = {}
    for k, row in ev.items():
        if k[1] not in texts:
            r = by_id.get(k[1])
            texts[k[1]] = (text_for(r) if r else None) or ""
        row["answer"] = recheck(row["answer"], texts[k[1]])
    ft = []
    for r in splits:
        panel = _votes(r, Stage.full_text.value)
        for v in panel["reviewers"]:
            a = ev.get(("ft_split", r["id"], v["r"]))
            if a:
                v["evidence"] = a["answer"]
        ft.append({**_item(r), "panel": panel, "panel_ta": _votes(r, Stage.title_abstract.value)})

    xvotes = _extraction_votes()
    ex = []
    for r in records:
        e = r.get("extraction") or {}
        if r.get("phase") != PrismaPhase.included.value or not e.get("unresolved"):
            continue
        votes = {k: field_values(v) for k, v in xvotes.get(r["id"], {}).items()}
        fields = []
        for f in e["unresolved"]:
            fields.append({"field": f, "kind": _field_kind(f),
                           "vocab": ROB_LEVELS if f.startswith("rob.") else VOCAB.get(f),
                           "options": [{"by": k, "value": votes[k].get(f),
                                        "evidence": ((ev.get(("extraction", r["id"], k)) or {}).get("answer") or {})
                                        .get("fields", {}).get(f)}
                                       for k in ("R1", "R3", "R2") if k in votes]})
        ex.append({**_item(r), "fields": fields,
                   "context": {k: e.get(k) for k in ("platform_class", "platform_name", "n_agents_min",
                                                      "n_agents_max", "propulsion", "control_architecture",
                                                      "phenomena", "theory_compared", "agreement",
                                                      "environment", "notes", "notes_alt")}})

    seeds = []
    for rid in _seed_ids(records):
        r = by_id[rid]
        stage = Stage.full_text.value if _votes(r, Stage.full_text.value) else Stage.title_abstract.value
        seeds.append({**_item(r), "stage": stage, "panel": _votes(r, stage)})

    queue = {"format": FORMAT, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "queues": {"ta_sample": ta, "ft_split": ft, "extraction": ex, "seeds": seeds}}
    body = json.dumps(queue["queues"], ensure_ascii=False, sort_keys=True).encode("utf-8")
    queue["queue_sha256"] = hashlib.sha256(body).hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(queue, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {k: len(v) for k, v in queue["queues"].items()}


def _key(row: dict) -> tuple:
    return (row["queue"], row["record_id"], row.get("field"))


def import_labels(path: Path, ledger: Path = LABELS) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{path} is not a {FORMAT} export")
    seen = {(*_key(r), r.get("at")) for r in read_jsonl(ledger)} if ledger.exists() else set()
    new = []
    for row in data.get("labels") or []:
        if row.get("queue") not in ("ta_sample", "ft_split", "extraction", "seeds") or not row.get("record_id"):
            continue
        if (*_key(row), row.get("at")) in seen:
            continue
        new.append({**row, "imported_from": Path(path).name, "queue_sha256": data.get("queue_sha256"),
                    "reviewer": data.get("reviewer") or REVIEWER})
    write_jsonl(ledger, new)
    return {"new_labels": len(new), "in_file": len(data.get("labels") or [])}


def latest_labels(ledger: Path = LABELS) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for row in read_jsonl(ledger) if ledger.exists() else []:
        k = _key(row)
        # Append-only: the last row per item wins, except that a judge never overrides the author.
        if row.get("reviewer") == JUDGE and out.get(k, {}).get("reviewer", REVIEWER) != JUDGE and k in out:
            continue
        out[k] = row
    return out


def _decision(label: dict, stage: Stage) -> dict:
    note = (label.get("note") or "").strip()
    seen = " (panel votes seen before deciding)" if label.get("saw_panel") else " (blind)"
    who = label.get("reviewer") or REVIEWER
    return Decision(reviewer=who, stage=stage, include=bool(label["include"]),
                    reason=None if label["include"] else (label.get("reason") or who),
                    at=date.fromisoformat((label.get("at") or date.today().isoformat())[:10]),
                    rationale=(note + seen).strip()).model_dump(mode="json")


def _set_decision(r: dict, d: dict) -> None:
    r["decisions"] = [x for x in r.get("decisions") or []
                      if not (x.get("reviewer") in (REVIEWER, JUDGE) and x.get("stage") == d["stage"])] + [d]


def apply(corpus: Path, ledger: Path = LABELS) -> dict:
    labels = latest_labels(ledger)
    counts: Counter[str] = Counter()
    with locked(corpus):
        records = read_jsonl(corpus)
        by_id = {r["id"]: r for r in records}
        for r in records:
            for alias in r.get("previous_ids") or []:
                by_id.setdefault(alias, r)
        for (queue, rid, field), lab in labels.items():
            r = by_id.get(rid)
            if r is None:
                counts["unknown_record"] += 1
                continue
            if queue == "extraction":
                e = r.get("extraction")
                if not e or "value" not in lab:
                    continue
                resolved = e.setdefault("author_resolved", {})
                resolved[field] = {"value": lab["value"], "chosen_from": lab.get("chosen_from"), "at": lab.get("at"),
                                   "by": lab.get("reviewer") or REVIEWER}
                e[field] = lab["value"]
                e["unresolved"] = [f for f in e.get("unresolved") or [] if f != field]
                counts["extraction_fields"] += 1
                continue
            if lab.get("include") is None:  # "unsure": kept in the ledger, not applied
                counts["unsure"] += 1
                continue
            stage = Stage.title_abstract if queue == "ta_sample" else Stage.full_text
            if queue == "seeds" and not _votes(r, Stage.full_text.value):
                stage = Stage.title_abstract
            _set_decision(r, _decision(lab, stage))
            if stage is Stage.title_abstract:
                if lab["include"] and r.get("phase") == PrismaPhase.screened_out.value:
                    r["phase"] = PrismaPhase.screened_in.value
                    counts["sent_to_full_text"] += 1
                elif not lab["include"] and r.get("phase") != PrismaPhase.screened_out.value:
                    counts["ta_exclude_not_applied"] += 1
            else:
                new = PrismaPhase.included if lab["include"] else PrismaPhase.excluded_eligibility
                if r.get("phase") != new.value:
                    counts[f"overridden_to_{new.value}"] += 1
                r["phase"] = new.value
            counts[f"applied_{queue}"] += 1
        rewrite_jsonl(corpus, records)
    return dict(counts)


def report(corpus: Path, ledger: Path = LABELS) -> dict:
    """Panel sensitivity/specificity against the author on the title/abstract sample, and
    agreement on full-text splits (PROTOCOL §6)."""

    labels = latest_labels(ledger)
    by_id = {}
    for r in read_jsonl(corpus):
        by_id[r["id"]] = r
        for alias in r.get("previous_ids") or []:
            by_id.setdefault(alias, r)
    out: dict = {}
    for queue, stage in (("ta_sample", Stage.title_abstract), ("ft_split", Stage.full_text)):
        tp = fn = tn = fp = not_blind = 0
        for (q, rid, _), lab in labels.items():
            if q != queue or rid not in by_id:
                continue
            if queue == "ta_sample":
                # Sensitivity rests on the independent (blind) answer, even if it was revised later.
                if lab.get("saw_panel") and not lab.get("blind"):
                    not_blind += 1
                lab = lab.get("blind") or lab
            if lab.get("include") is None:
                continue
            panel = _votes(by_id[rid], stage.value)
            if panel is None:
                continue
            if lab["include"]:
                tp, fn = tp + bool(panel["include"]), fn + (not panel["include"])
            else:
                tn, fp = tn + (not panel["include"]), fp + bool(panel["include"])
        n = tp + fn + tn + fp
        po = (tp + tn) / n if n else None
        pe = (((tp + fp) * (tp + fn) + (tn + fn) * (tn + fp)) / n**2) if n else None
        out[queue] = {"labelled": n, "author_include": tp + fn, "panel_tp": tp, "panel_fn": fn,
                      "panel_tn": tn, "panel_fp": fp,
                      "sensitivity": tp / (tp + fn) if tp + fn else None,
                      "specificity": tn / (tn + fp) if tn + fp else None,
                      "agreement": po,
                      "cohen_kappa": (po - pe) / (1 - pe) if n and pe is not None and pe < 1 else None,
                      "seen_panel_before_deciding": not_blind}
    out["extraction_fields_resolved"] = sum(1 for k in labels if k[0] == "extraction")
    out["seeds_labelled"] = sum(1 for k in labels if k[0] == "seeds")
    return out
