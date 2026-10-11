from types import SimpleNamespace

from amlr.fulltext import dispatch as d
from amlr.storage import read_jsonl, write_jsonl

CFG = SimpleNamespace(elsevier_api_key="k", elsevier_insttoken=None, wiley_tdm_token="t")


def test_is_pdf_requires_magic_and_size():
    assert d.is_pdf(b"%PDF-1.7" + b"x" * 20_000)
    assert not d.is_pdf(b"%PDF-1.7 tiny")
    assert not d.is_pdf(b"<html>" + b"x" * 20_000)


def test_slug_is_filesystem_safe():
    assert d.slug({"id": "doi:10.1103/PhysRevLett.120.188002"}) == "doi_10.1103_PhysRevLett.120.188002"


def test_routes_only_claim_their_publishers(monkeypatch):
    seen = []
    monkeypatch.setattr(d, "_get", lambda url, headers=None, timeout=60: (seen.append(url), (404, b"", ""))[1])
    monkeypatch.setattr(d, "_polite", lambda host, interval: None)
    assert d.r_elsevier("10.1103/x", CFG) is None and d.r_wiley("10.1016/x", CFG) is None
    assert seen == []  # wrong prefixes never hit the network
    d.r_aps("10.1103/physrevlett.120.188002", CFG)
    assert seen[-1] == "https://journals.aps.org/prl/pdf/10.1103/physrevlett.120.188002"
    n = len(seen)
    assert d.r_aps("10.1103/pv3d-7s54", CFG) is None and len(seen) == n  # new-style DOI: left to landing page


def test_acquire_falls_through_to_arxiv_and_records_route(tmp_path, monkeypatch):
    pdf = b"%PDF-1.5" + b"x" * 20_000
    monkeypatch.setattr(d, "PDF_DIR", tmp_path / "docs")
    monkeypatch.setattr(d, "TEXT_DIR", tmp_path / "text")
    monkeypatch.setattr(d, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(d, "DOI_ROUTES", [("springer", 1, lambda doi, cfg: None)])
    monkeypatch.setattr(d, "r_arxiv", lambda aid, cfg: pdf)
    monkeypatch.setattr(d, "extract_text", lambda p, r: None)
    row = d.acquire({"id": "doi:10.1007/abc", "doi": "10.1007/abc", "arxiv_id": "2101.00001"}, CFG)
    assert row["status"] == "retrieved" and row["route"] == "arxiv" and row["tier"] == 2
    assert row["tried"] == ["springer", "arxiv"]
    assert (tmp_path / "docs" / "doi_10.1007_abc.pdf").read_bytes() == pdf


def test_apply_and_finalize_phases(tmp_path, monkeypatch):
    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "acq.jsonl"
    monkeypatch.setattr(d, "LEDGER", ledger)
    write_jsonl(corpus, [{"id": "a", "phase": "screened_in"}, {"id": "b", "phase": "screened_in"}])
    write_jsonl(ledger, [
        {"record_id": "a", "status": "retrieved", "route": "aps", "pdf": "docs/a.pdf", "bytes": 1, "sha256": "x", "text": "t.txt"},
        {"record_id": "b", "status": "not_retrieved", "tried": ["landing_page", "unpaywall"]},
    ])
    d.apply(corpus)
    rows = {r["id"]: r for r in read_jsonl(corpus)}
    assert rows["a"]["phase"] == "assessed" and rows["b"]["phase"] == "fulltext_sought"
    assert d.finalize(corpus) == 1
    assert {r["id"]: r["phase"] for r in read_jsonl(corpus)}["b"] == "fulltext_not_retrieved"
