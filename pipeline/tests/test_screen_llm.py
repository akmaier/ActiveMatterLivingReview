import json

import pytest

from amlr.llm import PANEL, parse_json_object
from amlr.schema import PrismaPhase, Stage
from amlr.screen_llm import aggregate, agreement_report, cohen_kappa, fleiss_kappa, run_panel
from amlr.storage import read_jsonl, write_jsonl


def test_parse_json_tolerates_reasoning_and_fences():
    text = '[THINK]maybe {"decision": "exclude"}[/THINK]\n```json\n{"decision": "include", "reason": null}\n```'
    assert parse_json_object(text, "decision")["decision"] == "include"
    assert parse_json_object('<think>x</think>{"decision":"exclude","reason":"E2"}', "decision")["reason"] == "E2"
    with pytest.raises(ValueError):
        parse_json_object("no json here", "decision")
    # Raw control characters inside strings (copied from PDF text) are tolerated.
    assert parse_json_object('{"decision": "include", "rationale": "order \x03 parameter"}', "decision")["decision"] == "include"


def _v(inc, reason=None):
    return {"include": inc, "reason": reason}


def test_majority_rule_and_reason_precedence():
    assert aggregate([_v(True), _v(True), _v(False, "E2")])["include"] is True
    assert aggregate([_v(True), _v(False, "E1"), _v(False, "E1")]) == {"include": False, "votes": "1/3", "reason": "E1"}
    # All three codes differ: highest precedence (E5 > E4 > E6 > E1 > E2 > E3) wins.
    assert aggregate([_v(False, "E3"), _v(False, "E5"), _v(False, "E1")])["reason"] == "E5"
    assert aggregate([_v(True), _v(False, "E2"), _v(False, "E2")], liberal=True)["include"] is True


def test_kappas():
    assert cohen_kappa([True, False, True, False], [True, False, True, False]) == pytest.approx(1.0)
    assert cohen_kappa([True, True], [True, True]) is None
    assert fleiss_kappa([[True, True, True], [False, False, False]]) == pytest.approx(1.0)


def _fake_transport(answers):
    """answers: model -> list of contents, consumed in order (per model)."""
    calls = []

    def transport(url, headers, body, timeout):
        model = json.loads(body)["model"]
        calls.append(model)
        content = answers[model].pop(0) if isinstance(answers[model], list) else answers[model]
        return {"model": model, "choices": [{"message": {"content": content}, "finish_reason": "stop"}]}

    return transport, calls


def test_run_panel_votes_applies_and_resumes(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    ledger = tmp_path / "votes.jsonl"
    write_jsonl(corpus, [
        {"id": "a", "title": "Collective motion of vibrated polar disks", "abstract": "We study ..."},
        {"id": "b", "title": "A single bristlebot in a maze", "abstract": "One robot ..."},
    ])
    inc = '{"decision": "include", "reason": null, "confidence": 0.9, "rationale": "ok"}'
    exc = '{"decision": "exclude", "reason": "E1", "confidence": 0.8, "rationale": "single"}'
    r1, r2, r3 = PANEL["R1"], PANEL["R2"], PANEL["R3"]
    # Ordering inside a model's queue is not guaranteed under threads, so use workers=1.
    transport, calls = _fake_transport({r1: [inc, exc], r2: [inc, exc], r3: [exc, exc]})

    out = run_panel(Stage.title_abstract, corpus, mode="full", workers=1, transport=transport, ledger_path=ledger)
    assert out["votes_cast"] == 6 and out["vote_errors"] == 0 and out["decided"] == 2
    rows = {r["id"]: r for r in read_jsonl(corpus)}
    assert rows["a"]["phase"] == PrismaPhase.screened_in.value
    assert rows["b"]["phase"] == PrismaPhase.screened_out.value
    assert rows["b"]["decisions"][-1] == {
        "reviewer": "panel", "stage": "title_abstract", "include": False, "reason": "E1",
        "votes": "0/3", "prompt_sha256": out["prompt_sha256"],
    }

    # Second run: nothing eligible (phases advanced), no new calls.
    n_calls = len(calls)
    again = run_panel(Stage.title_abstract, corpus, mode="full", workers=1, transport=transport, ledger_path=ledger)
    assert again["votes_cast"] == 0 and len(calls) == n_calls

    rep = agreement_report(Stage.title_abstract, ledger_path=ledger)
    assert rep["records_fully_voted"] == 2
    assert rep["include_votes_distribution"] == {"0/3": 1, "1/3": 0, "2/3": 1, "3/3": 0}


def test_unparseable_vote_is_recorded_and_retried(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    ledger = tmp_path / "votes.jsonl"
    write_jsonl(corpus, [{"id": "a", "title": "t", "abstract": "x"}])
    good = '{"decision": "include", "reason": null}'
    transport, _ = _fake_transport({PANEL["R1"]: ["garbage", good], PANEL["R2"]: [good], PANEL["R3"]: [good]})
    first = run_panel(Stage.title_abstract, corpus, mode="full", workers=1, transport=transport, ledger_path=ledger)
    assert first["vote_errors"] == 1 and first["decided"] == 0
    second = run_panel(Stage.title_abstract, corpus, mode="full", workers=1, transport=transport, ledger_path=ledger)
    assert second["votes_cast"] == 1 and second["decided"] == 1


def test_adaptive_mode_calls_r3_only_when_it_can_matter(tmp_path):
    from amlr.screen_llm import in_audit

    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "votes.jsonl"
    # Pick ids outside the audit sample so R3 is called only for ties.
    ids = [f"rec{i}" for i in range(200) if not in_audit(f"rec{i}")][:3]
    write_jsonl(corpus, [
        {"id": ids[0], "title": "agree include", "abstract": "x"},
        {"id": ids[1], "title": "disagree", "abstract": "x"},
        {"id": ids[2], "title": "agree exclude, no abstract"},
    ])
    inc = '{"decision": "include", "reason": null}'
    exc = '{"decision": "exclude", "reason": "E2"}'
    by_title = {
        "agree include": {"R1": inc, "R2": inc, "R3": exc},
        "disagree": {"R1": inc, "R2": exc, "R3": inc},
        "agree exclude, no abstract": {"R1": exc, "R2": exc, "R3": exc},
    }
    model_to_rv = {m: rv for rv, m in PANEL.items()}
    calls = []

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        rv = model_to_rv[payload["model"]]
        title = payload["messages"][1]["content"].split("Title: ", 1)[1].split("\n", 1)[0]
        calls.append((rv, title))
        return {"model": payload["model"], "choices": [{"message": {"content": by_title[title][rv]}, "finish_reason": "stop"}]}

    out = run_panel(Stage.title_abstract, corpus, workers=1, tiebreak_workers=1, transport=transport, ledger_path=ledger)
    r3_titles = sorted(t for rv, t in calls if rv == "R3")
    assert r3_titles == ["agree exclude, no abstract", "disagree"]
    assert out["decided"] == 3
    rows = {r["id"]: r for r in read_jsonl(corpus)}
    assert rows[ids[0]]["decisions"][-1]["votes"] == "2/2"
    assert rows[ids[1]]["phase"] == PrismaPhase.screened_in.value
    assert rows[ids[2]]["phase"] == PrismaPhase.screened_out.value


def test_invalidation_marker_voids_earlier_full_text_votes():
    from amlr.screen_llm import _valid_votes

    vote = lambda rid, rv: {"record_id": rid, "stage": "full_text", "reviewer": rv, "prompt_sha256": "s", "include": True}
    ledger = [vote("a", "R1"), vote("a", "R2"), vote("b", "R1"),
              {"record_id": "a", "stage": "full_text", "invalidated_at": "t", "reason": "preview"},
              vote("a", "R1")]
    v = _valid_votes(ledger, Stage.full_text, "s")
    assert set(v["a"]) == {"R1"}  # only the vote cast after the invalidation counts
    assert set(v["b"]) == {"R1"}


def test_dropped_connection_is_recorded_not_fatal(tmp_path):
    import http.client

    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "votes.jsonl"
    write_jsonl(corpus, [{"id": "a", "title": "t", "abstract": "x"}])

    def transport(url, headers, body, timeout):
        raise http.client.RemoteDisconnected("Remote end closed connection without response")

    import amlr.llm as llm
    orig = llm.time.sleep
    llm.time.sleep = lambda s: None
    try:
        out = run_panel(Stage.title_abstract, corpus, mode="full", workers=1, transport=transport, ledger_path=ledger)
    finally:
        llm.time.sleep = orig
    assert out["vote_errors"] == 3 and out["decided"] == 0
    assert all("network error" in v["error"] for v in read_jsonl(ledger))
