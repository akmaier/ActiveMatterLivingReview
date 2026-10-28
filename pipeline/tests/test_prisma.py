from datetime import date

from amlr.prisma import compute_counts, render_flow_svg
from amlr.schema import PrismaPhase as P


def test_empty_corpus_counts_are_zero():
    c = compute_counts([])
    assert c["identified_db"] == 0
    assert c["included_studies"] == 0


def test_counts_follow_prisma_arithmetic():
    rows = [
        {"phase": P.identified.value},
        {"phase": P.duplicate.value},
        {"phase": P.screened_out.value},
        {"phase": P.screened_in.value},
        {"phase": P.fulltext_not_retrieved.value},
        {"phase": P.excluded_eligibility.value, "decisions": [{"reason": "simulation only"}]},
        {"phase": P.included.value},
    ]
    c = compute_counts(rows)
    assert c["identified_db"] == 7
    assert c["duplicates_removed"] == 1
    assert c["awaiting_screening"] == 1
    assert c["screened"] == 5
    assert c["excluded_screening"] == 1
    assert c["sought"] == 4
    assert c["not_retrieved"] == 1
    assert c["assessed"] == 2
    assert c["excluded_eligibility_reasons"] == {"simulation only": 1}
    assert c["included_studies"] == 1


def test_svg_contains_counts_and_escapes_reasons():
    rows = [{"phase": P.excluded_eligibility.value, "decisions": [{"reason": "a<b & c"}]}]
    svg = render_flow_svg(compute_counts(rows, today=date(2026, 10, 11)))
    assert svg.startswith("<svg")
    assert "Reports excluded (n = 1)" in svg
    assert "a&lt;b &amp; c: 1" in svg
    assert "Snapshot 2026-10-11" in svg


def test_flow_boxes_reconcile_and_list_every_reason():
    from amlr.prisma import flow_boxes

    c = {"snapshot_date": "2026-10-17", "identified_db": 100, "identified_registers": 0,
         "duplicates_removed": 10, "screened": 90, "excluded_screening": 40, "sought": 50,
         "not_retrieved": 12, "assessed_on_abstract_only": 8, "abstract_only_included": 3,
         "assessed": 38, "excluded_eligibility": 25, "excluded_full_text": 20,
         "excluded_abstract_only": 5, "included_full_text": 17, "awaiting_decision": 1,
         "excluded_full_text_reasons": {"E1": 2, "E2": 5, "E3": 4, "E4": 1, "E5": 6, "E6": 2},
         "excluded_abstract_only_reasons": {"E2": 1, "E5": 4},
         "included_studies": 20, "included_reports": 20}
    assert c["assessed"] == c["excluded_full_text"] + c["awaiting_decision"] + c["included_full_text"]
    boxes, arrows = flow_boxes(c)
    text = {b["id"]: " ".join(b["lines"]) for b in boxes}
    assert "Reports excluded (n = 20)" in text["exe"]
    assert all(f"{k}: {v}" in text["exe"] for k, v in c["excluded_full_text_reasons"].items())
    assert "Awaiting decision (n = 1)" in text["exe"]
    assert "Excluded (n = 5)" in text["aoe"] and "Included (n = 3)" in text["aoe"]
    assert "on full text 17" in text["inc"] and "on abstract only 3" in text["inc"]
    assert ("aoe", "inc") in arrows
