import json

from amlr import search, update
from amlr.storage import read_jsonl


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_merge_keeps_previous_state_and_adds_only_unmatched_rows(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    old = {"id": "doi:10.1/a", "doi": "10.1/a", "title": "Flocking of vibrated robots in a circular arena",
           "year": 2024, "source_ids": {"openalex": "W1"}, "phase": "included",
           "decisions": [{"stage": "full_text", "decision": "include"}], "extraction": {"platform_class": "x"}}
    _write(corpus, [old])
    rows = [
        {"id": "arxiv:2610.1", "doi": "10.1/A", "title": "Flocking of vibrated robots in a circular arena",
         "year": 2024, "source_ids": {"arxiv": "2610.1"}, "provenance": {"arxiv": {}}},
        {"id": "pmid:9", "doi": "10.2/b", "title": "Clustering of light-driven microrobots under feedback",
         "year": 2026, "source_ids": {"pubmed": "9"}, "provenance": {"pubmed": {}}},
        {"id": "crossref:10.2/b", "doi": "10.2/b", "title": "Clustering of light-driven microrobots under feedback",
         "year": 2026, "source_ids": {"crossref": "10.2/b"}, "provenance": {"crossref": {}}},
    ]
    stats = update.merge_new(rows, "2026-11-11", corpus)
    assert stats == {"rows": 3, "already_in_review": 1, "duplicates_within_update": 1, "new_records": 1}
    out = {r["id"]: r for r in read_jsonl(corpus)}
    kept = out["doi:10.1/a"]
    assert kept["phase"] == "included" and kept["decisions"] == old["decisions"] and kept["extraction"] == old["extraction"]
    assert set(kept["source_ids"]) == {"openalex", "arxiv"}
    new = out["doi:10.2/b"]
    assert new["phase"] == "identified" and new["identified_in_update"] == "2026-11-11"
    assert set(new["sources"]) == {"crossref", "pubmed"}


def test_state_round_trip_drops_abstracts_of_excluded_records(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(update, "STATE_CORPUS", tmp_path / "state" / "corpus.jsonl.gz")
    monkeypatch.setattr(update, "STATE_META", tmp_path / "state" / "state.json")
    corpus = tmp_path / "corpus.jsonl"
    _write(corpus, [{"id": "a", "phase": "screened_out", "abstract": "long"},
                    {"id": "b", "phase": "included", "abstract": "kept"}])
    meta = update.save_state(corpus, last_search="2026-11-11")
    assert meta["records"] == 2 and meta["last_search"] == "2026-11-11"
    corpus.unlink()
    update.restore_state(corpus)
    assert {r["id"]: r["abstract"] for r in read_jsonl(corpus)} == {"a": None, "b": "kept"}
    assert update.window()[0] == "2026-10-28"  # last search minus the 14-day overlap


def test_window_filters_reach_every_source_url():
    search.WINDOW = "2026-10-01"
    try:
        assert "from_publication_date%3A2025-10-01" in search.openalex_url("q")
        assert "submittedDate" in search.arxiv_url("q")
        assert "mindate=2026%2F10%2F01" in search.pubmed_url("q")
        assert "submittedDate_tdate" in search.hal_url("q")
        assert "FIRST_PDATE" in search.europepmc_url("q")
        assert "entdate" in search.ads_url("q")
    finally:
        search.WINDOW = None
    assert "from_publication_date" not in search.openalex_url("q")
