from amlr.dedup import canonical_doi, carry_over, jaccard, merge_records, normalized_title


def test_canonical_doi_strips_prefix_and_lowercases():
    assert canonical_doi("https://doi.org/10.1038/NMAT3281") == "10.1038/nmat3281"
    assert canonical_doi("doi.org/10.1038/NMAT3281") == "10.1038/nmat3281"
    assert canonical_doi(None) is None


def test_normalized_title_and_jaccard():
    assert normalized_title("Active matter: a review!") == "active matter a review"
    assert jaccard("active matter review", "active matter review") == 1.0


def test_same_doi_merges_and_unions_source_ids():
    rows = [
        {"id": "openalex:W1", "doi": "10.1/x", "title": "Foo", "source_ids": {"openalex": "W1"}},
        {"id": "crossref:10.1/x", "doi": "https://doi.org/10.1/X", "title": "Foo", "source_ids": {"crossref": "10.1/x"}},
    ]
    [m] = merge_records(rows)
    assert m["source_ids"] == {"openalex": "W1", "crossref": "10.1/x"}
    assert m["id"] == "doi:10.1/x" and m["sources"] == ["crossref", "openalex"]


def test_preprint_and_journal_version_become_one_record():
    rows = [
        {"id": "arxiv:1801.00001", "arxiv_id": "1801.00001v2", "doi": None, "year": 2018,
         "title": "Boundaries control collective dynamics of inertial self-propelled robots",
         "abstract": "short", "source_ids": {"arxiv": "1801.00001"}},
        {"id": "openalex:W2", "doi": "10.1103/PhysRevLett.120.188002", "year": 2018,
         "title": "Boundaries Control Collective Dynamics of Inertial Self-Propelled Robots",
         "abstract": "a longer abstract text", "source_ids": {"openalex": "W2"}},
        {"id": "ads:2018PhRvL", "doi": "10.48550/arXiv.1801.00001", "year": 2018, "title": "different title",
         "source_ids": {"ads": "2018PhRvL"}},
    ]
    [m] = merge_records(rows)
    assert m["doi"] == "10.1103/physrevlett.120.188002"  # journal DOI beats the arXiv DOI
    assert m["arxiv_id"] == "1801.00001"
    assert m["abstract"] == "a longer abstract text"
    assert m["merged_from"] == 3


def test_short_identical_titles_are_not_merged():
    rows = [{"id": "a", "title": "Active matter", "year": 2010, "source_ids": {"x": "a"}},
            {"id": "b", "title": "Active matter", "year": 2020, "source_ids": {"x": "b"}}]
    assert len(merge_records(rows)) == 2


def test_carry_over_keeps_screening_state():
    old = [{"id": "doi:10.1/x", "doi": "10.1/x", "phase": "screened_in", "decisions": [{"reviewer": "panel"}]}]
    new = merge_records([{"id": "openalex:W1", "doi": "10.1/x", "title": "Foo", "source_ids": {"openalex": "W1"}}])
    assert carry_over(new, old) == 1
    assert new[0]["phase"] == "screened_in"


def test_carry_over_keeps_previous_id_and_records_aliases():
    old = [{"id": "arxiv:1801.00001", "arxiv_id": "1801.00001", "phase": "identified", "source_ids": {"arxiv": "1801.00001"}},
           {"id": "doi:10.1/j", "doi": "10.1/j", "phase": "included", "source_ids": {"crossref": "10.1/j"}}]
    new = merge_records([{"id": "openalex:W9", "doi": "10.1/j", "arxiv_id": "1801.00001", "title": "Same paper",
                          "source_ids": {"openalex": "W9"}}])
    assert carry_over(new, old) == 1
    assert new[0]["id"] == "doi:10.1/j" and new[0]["phase"] == "included"
    assert new[0]["previous_ids"] == ["arxiv:1801.00001"]


def test_titles_with_dropped_spaces_merge():
    rows = [{"id": "doi:10.1007/x", "doi": "10.1007/x", "year": 2022, "source_ids": {"crossref": "10.1007/x"},
             "title": "Generating and Analyzing Collective Step-Climbing Behavior in a Multi-legged Robotic Swarm"},
            {"id": "openalex:W7", "year": 2022, "source_ids": {"openalex": "W7"},
             "title": "Generating andAnalyzing Collective Step-Climbing Behavior inaMulti-legged Robotic Swarm"}]
    assert len(merge_records(rows)) == 1


def test_two_ids_from_one_source_are_both_kept():
    rows = [{"id": "openalex:W1", "doi": "10.1/j", "title": "A long enough title for merging here", "year": 2024,
             "source_ids": {"openalex": "W1"}},
            {"id": "openalex:W2", "doi": "10.1/j", "title": "A long enough title for merging here", "year": 2024,
             "source_ids": {"openalex": "W2"}}]
    [m] = merge_records(rows)
    assert m["source_id_list"] == [("openalex", "W1"), ("openalex", "W2")]
