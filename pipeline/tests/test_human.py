import json

from amlr import human as h
from amlr.storage import read_jsonl, write_jsonl


def _panel(stage, include, votes, reason=None):
    return [{"reviewer": "R1", "stage": stage, "include": include, "reason": reason, "at": "2026-10-11"},
            {"reviewer": "panel", "stage": stage, "include": include, "reason": reason, "votes": votes}]


def _export(tmp_path, labels):
    f = tmp_path / "human-check-1.json"
    f.write_text(json.dumps({"format": h.FORMAT, "queue_sha256": "x", "labels": labels}))
    return f


def test_import_apply_and_report(tmp_path, monkeypatch):
    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "labels.jsonl"
    write_jsonl(corpus, [
        {"id": "a", "phase": "screened_out", "decisions": _panel("title_abstract", False, "0/2", "E2")},
        {"id": "b", "phase": "included", "decisions": _panel("full_text", True, "2/3")},
        {"id": "c", "phase": "included", "extraction": {"unresolved": ["propulsion"], "propulsion": None}},
    ])
    f = _export(tmp_path, [
        {"queue": "ta_sample", "record_id": "a", "include": True, "saw_panel": False,
         "blind": {"include": True, "reason": None}, "at": "2026-10-14T10:00:00Z"},
        {"queue": "ft_split", "record_id": "b", "include": False, "reason": "E2", "note": "no hardware",
         "saw_panel": True, "at": "2026-10-14T10:01:00Z"},
        {"queue": "extraction", "record_id": "c", "field": "propulsion", "value": "wheels",
         "chosen_from": "R3", "at": "2026-10-14T10:02:00Z"},
    ])
    assert h.import_labels(f, ledger) == {"new_labels": 3, "in_file": 3}
    assert h.import_labels(f, ledger)["new_labels"] == 0  # re-importing the same export adds nothing
    counts = h.apply(corpus, ledger)
    assert counts["sent_to_full_text"] == 1 and counts["overridden_to_excluded_eligibility"] == 1
    rows = {r["id"]: r for r in read_jsonl(corpus)}
    assert rows["a"]["phase"] == "screened_in"
    assert rows["b"]["phase"] == "excluded_eligibility"
    assert rows["b"]["decisions"][-1]["reviewer"] == "author" and rows["b"]["decisions"][-1]["reason"] == "E2"
    assert rows["c"]["extraction"]["propulsion"] == "wheels" and rows["c"]["extraction"]["unresolved"] == []
    rep = h.report(corpus, ledger)
    assert rep["ta_sample"]["panel_fn"] == 1 and rep["ta_sample"]["sensitivity"] == 0.0
    assert rep["ft_split"]["panel_fp"] == 1


def test_ta_exclude_does_not_undo_full_text_and_unsure_is_not_applied(tmp_path):
    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "labels.jsonl"
    write_jsonl(corpus, [
        {"id": "a", "phase": "included", "decisions": _panel("title_abstract", True, "2/2")},
        {"id": "b", "phase": "included", "decisions": _panel("full_text", True, "2/3")},
    ])
    h.import_labels(_export(tmp_path, [
        {"queue": "ta_sample", "record_id": "a", "include": False, "reason": "E3", "at": "2026-10-14T10:00:00Z"},
        {"queue": "ft_split", "record_id": "b", "include": None, "at": "2026-10-14T10:00:00Z"},
    ]), ledger)
    counts = h.apply(corpus, ledger)
    assert counts["ta_exclude_not_applied"] == 1 and counts["unsure"] == 1
    assert {r["id"]: r["phase"] for r in read_jsonl(corpus)} == {"a": "included", "b": "included"}


def test_author_resolved_fields_survive_reextraction(tmp_path):
    from amlr.extract import _apply

    corpus = tmp_path / "corpus.jsonl"
    write_jsonl(corpus, [{"id": "c", "phase": "included", "extraction": {
        "propulsion": "wheels", "unresolved": [],
        "author_resolved": {"propulsion": {"value": "wheels", "chosen_from": "R3", "at": "t"}}}}])
    _apply(corpus, {"c": {"record_id": "c", "propulsion": None, "unresolved": ["propulsion"]}})
    e = read_jsonl(corpus)[0]["extraction"]
    assert e["propulsion"] == "wheels" and e["unresolved"] == [] and "author_resolved" in e


def test_quote_check_flags_fabricated_evidence():
    from amlr.evidence import _clean_evidence, _grams, _norm, verify

    text = "We built 12 robots.\nThe polar order para-\nmeter rises above 0.8 at high density."
    assert verify("the polar order parameter rises above 0.8", text) == "verbatim"
    assert verify("robots formed a perfect crystal at low density", text) == "not_found"
    ev = _clean_evidence([{"criterion": "I3", "quote": "We built 12 robots."}, {"quote": 3}], text,
                         _grams(_norm(text).split()))
    assert ev == [{"criterion": "I3", "quote": "We built 12 robots.", "check": "verbatim"}]


def test_judge_never_overrides_author(tmp_path):
    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "labels.jsonl"
    write_jsonl(corpus, [{"id": "b", "phase": "included", "decisions": _panel("full_text", True, "2/3")}])
    h.import_labels(_export(tmp_path, [{"queue": "ft_split", "record_id": "b", "include": True,
                                        "at": "2026-10-14T10:00:00Z"}]), ledger)
    judged = tmp_path / "judge.json"
    judged.write_text(json.dumps({"format": h.FORMAT, "reviewer": h.JUDGE, "labels": [
        {"queue": "ft_split", "record_id": "b", "include": False, "reason": "E2", "at": "2026-10-17T10:00:00Z"}]}))
    h.import_labels(judged, ledger)
    h.apply(corpus, ledger)
    r = read_jsonl(corpus)[0]
    assert r["phase"] == "included" and r["decisions"][-1]["reviewer"] == "author"
