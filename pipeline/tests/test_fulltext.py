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


def test_retry_skips_routes_that_already_failed(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(d, "DOI_ROUTES", [("springer", 1, lambda doi, cfg: called.append("springer")),
                                          ("semantic_scholar", 2, lambda doi, cfg: called.append("s2"))])
    monkeypatch.setattr(d, "arxiv_id_by_title", lambda t: called.append("arxiv_title"))
    row = d.acquire({"id": "x", "doi": "10.1007/x", "title": "t"}, CFG, skip={"springer"})
    assert called == ["s2", "arxiv_title"]
    assert row["status"] == "not_retrieved"
    assert row["tried"] == ["springer", "semantic_scholar", "arxiv_title"]  # earlier failures first


def test_rate_limited_route_is_inconclusive_not_tried(monkeypatch):
    def throttled(doi, cfg):
        raise d.Inconclusive("HTTP 429")

    monkeypatch.setattr(d, "DOI_ROUTES", [("semantic_scholar", 2, throttled)])
    monkeypatch.setattr(d, "arxiv_id_by_title", lambda t: None)
    row = d.acquire({"id": "x", "doi": "10.1109/x", "title": "a title"}, CFG)
    assert row["inconclusive"] == ["semantic_scholar"]
    assert "semantic_scholar" not in row["tried"] and row["tried"] == ["arxiv_title"]


def test_elsevier_xml_text_keeps_body_drops_markup():
    xml = ('<x><dc:title>Swarm &amp; order</dc:title><ce:abstract-sec><ce:simple-para>Abstract text.</ce:simple-para>'
           '</ce:abstract-sec><ce:sections><ce:section><ce:section-title>Introduction</ce:section-title>'
           '<ce:para>Robots align <ce:cross-ref refid="b1">[1]</ce:cross-ref> fast.</ce:para></ce:section>'
           '</ce:sections><ce:caption><ce:simple-para>Fig. 1. Order parameter.</ce:simple-para></ce:caption></x>')
    t = d.elsevier_xml_text(xml)
    assert "Swarm & order" in t and "Introduction" in t and "Robots align" in t and "Order parameter" in t
    assert "[1]" not in t and "<" not in t


def test_jats_text_extracts_title_abstract_body():
    xml = ('<article><article-title>Robot flocks</article-title><abstract><p>Short.</p></abstract>'
           '<body><sec><title>Results</title><p>Order rises <xref>[2]</xref> sharply.</p>'
           '<fig><caption><p>Fig 1</p></caption></fig></sec></body></article>')
    t = d.jats_text(xml)
    assert "Robot flocks" in t and "Results" in t and "Order rises" in t and "[2]" not in t


def test_apply_keeps_no_full_report_records_out_of_retrieval(tmp_path, monkeypatch):
    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "acq.jsonl"
    monkeypatch.setattr(d, "LEDGER", ledger)
    write_jsonl(corpus, [{"id": "a", "phase": "fulltext_sought"}])
    write_jsonl(ledger, [{"record_id": "a", "status": "not_retrieved", "tried": ["unpaywall"]},
                         {"record_id": "a", "status": "no_full_report", "reason": "conference abstract only"}])
    d.apply(corpus)
    [r] = read_jsonl(corpus)
    assert r["phase"] == "fulltext_not_retrieved" and r["failure_reason"] == "conference abstract only"


def test_abstract_only_marking_counts_and_label(tmp_path, monkeypatch):
    from amlr.prisma import compute_counts
    from amlr.schema import Stage
    from amlr.screen_llm import load_prompt, render_record

    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "acq.jsonl"
    monkeypatch.setattr(d, "LEDGER", ledger)
    monkeypatch.setattr(d, "TEXT_DIR", tmp_path / "text")
    monkeypatch.setattr(d, "REPO_ROOT", tmp_path)
    write_jsonl(corpus, [{"id": "a", "phase": "fulltext_sought", "title": "T", "abstract": "Robots flock."},
                         {"id": "b", "phase": "fulltext_sought", "title": "U"}])
    assert d.mark_abstract_only(corpus, ["a", "b"], "unobtainable") == {"abstract_only": 1, "no_abstract_not_retrieved": 1}
    rows = {r["id"]: r for r in read_jsonl(corpus)}
    assert rows["a"]["phase"] == "assessed" and rows["b"]["phase"] == "fulltext_not_retrieved"
    c = compute_counts(list(rows.values()))
    assert c["not_retrieved"] == 2 and c["assessed_on_abstract_only"] == 1 and c["assessed"] == 0
    _, template, _ = load_prompt()
    assert "Abstract only (full text unavailable)" in render_record(template, rows["a"], Stage.full_text, "x")
    d.apply(corpus)  # apply() must not undo the abstract-only status
    assert {r["id"]: r for r in read_jsonl(corpus)}["a"]["assessment_basis"] == "abstract_only"


def test_unobtainable_records_survive_apply(tmp_path, monkeypatch):
    corpus, ledger = tmp_path / "corpus.jsonl", tmp_path / "acq.jsonl"
    monkeypatch.setattr(d, "LEDGER", ledger)
    monkeypatch.setattr(d, "TEXT_DIR", tmp_path / "text")
    write_jsonl(corpus, [{"id": "b", "phase": "fulltext_sought", "title": "U"}])
    write_jsonl(ledger, [{"record_id": "b", "status": "not_retrieved", "tried": ["springer"]}])
    d.mark_abstract_only(corpus, ["b"], "unobtainable")
    d.apply(corpus)
    assert read_jsonl(corpus)[0]["phase"] == "fulltext_not_retrieved"


def test_broken_transfer_is_a_failed_attempt(monkeypatch):
    import http.client

    class Boom:
        def __enter__(self):
            raise http.client.IncompleteRead(b"x" * 10, 100)

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(d.urllib.request, "urlopen", lambda *a, **k: Boom())
    assert d._get("https://example.org/x.pdf") == (0, b"", "")


def test_network_failure_makes_route_inconclusive(monkeypatch):
    def flaky(doi, cfg):
        return d._get("https://unreachable.invalid/x")[1] or None

    monkeypatch.setattr(d, "DOI_ROUTES", [("springer", 1, flaky)])
    monkeypatch.setattr(d.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("network down")))
    monkeypatch.setattr(d, "arxiv_id_by_title", lambda t: None)
    row = d.acquire({"id": "x", "doi": "10.1007/x", "title": "a b c"}, CFG)
    assert row["inconclusive"] == ["springer"] and "springer" not in row["tried"]
