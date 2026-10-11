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
