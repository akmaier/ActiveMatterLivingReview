import json

from amlr.extract import disputed, reconcile, run
from amlr.llm import PANEL
from amlr.storage import read_jsonl, write_jsonl

BASE = {
    "platform_class": "vibration_driven_robots", "platform_name": "Hexbug", "n_agents_min": 10,
    "n_agents_max": 100, "agent_size_mm": 40, "propulsion": "vibration",
    "interaction_modality": ["steric_contact"], "control_architecture": "no_control_passive_rules",
    "environment": "circular arena", "phenomena": ["flocking_polar_order", "boundary_accumulation"],
    "observables": ["polar order"], "theory_compared": ["active_brownian_particles"], "agreement": "quantitative",
    "n_independent_runs": 5, "code_available": False, "data_available": None,
    "rob": {k: {"rating": "low", "why": "ok"} for k in [
        "D1_replication", "D2_agent_heterogeneity", "D3_finite_size_and_boundaries",
        "D4_measurement_validity", "D5_data_code_availability", "D6_quantitative_theory_comparison"]},
    "notes": None,
}


def test_comparison_rules():
    b = dict(BASE, n_agents_max=105, phenomena=["boundary_accumulation", "flocking_polar_order"], platform_name="HEXBUG nano")
    assert disputed(BASE, b) == []  # counts within 10 %, sets order-free, free text not compared
    c = dict(BASE, propulsion="legs", n_agents_max=200)
    assert set(disputed(BASE, c)) == {"propulsion", "n_agents_max"}


def test_reconcile_majority_and_unresolved():
    b = dict(BASE, propulsion="legs", agreement="qualitative")
    arb = dict(BASE, propulsion="legs", agreement="none")
    final, unresolved = reconcile(BASE, b, arb)
    assert final["propulsion"] == "legs"
    assert final["agreement"] is None and unresolved == ["agreement"]
    assert final["rob.D1_replication"] == "low"


def test_run_calls_arbiter_only_for_disputes(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    write_jsonl(corpus, [{"id": "a", "phase": "included", "title": "t", "fulltext_txt_path": "x"},
                         {"id": "b", "phase": "included", "title": "u", "fulltext_txt_path": "y"}])
    answers = {("R1", "t"): BASE, ("R3", "t"): BASE,
               ("R1", "u"): BASE, ("R3", "u"): dict(BASE, propulsion="legs"), ("R2", "u"): dict(BASE, propulsion="legs")}
    rv_of = {m: rv for rv, m in PANEL.items()}
    calls = []

    def transport(url, headers, body, timeout):
        p = json.loads(body)
        title = p["messages"][1]["content"].split("Title: ", 1)[1].split("\n", 1)[0]
        rv = rv_of[p["model"]]
        calls.append((rv, title))
        return {"model": p["model"], "choices": [{"message": {"content": json.dumps(answers[(rv, title)])}, "finish_reason": "stop"}]}

    out = run(corpus, lambda r: "full text " * 100, workers=1, transport=transport,
              ledger=tmp_path / "votes.jsonl", final_path=tmp_path / "final.jsonl")
    assert out["extracted"] == 2 and out["with_unresolved_fields"] == 0
    assert ("R2", "t") not in calls and ("R2", "u") in calls
    rows = {r["id"]: r for r in read_jsonl(corpus)}
    assert rows["b"]["extraction"]["propulsion"] == "legs"
