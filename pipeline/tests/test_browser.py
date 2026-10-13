from amlr.fulltext.browser import CHALLENGE, pdf_url, plan


def test_plan_prefers_ieee_arnumber_then_doi_landing():
    assert plan({"source_ids": {"ieee": "8048084"}, "doi": "10.1109/x"}) == (
        "ieeexplore.ieee.org", "https://ieeexplore.ieee.org/document/8048084")
    assert plan({"doi": "10.1109/LRA.2020.1"}) == ("ieeexplore.ieee.org", "https://doi.org/10.1109/lra.2020.1")
    assert plan({"doi": "10.1126/science.abc"})[0] == "www.science.org"
    assert plan({"source_ids": {"ieee": "tdeadbeef"}}) is None  # title-hash ids have no landing page


def test_pdf_url_patterns_and_meta_fallback():
    assert pdf_url("ieeexplore.ieee.org", {}, "https://ieeexplore.ieee.org/document/123/", "") == \
        "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=123"
    assert pdf_url("www.pnas.org", {"doi": "10.1073/pnas.1"}, "", "") == "https://www.pnas.org/doi/pdf/10.1073/pnas.1?download=true"
    html = '<meta name="citation_pdf_url" content="https://pub.example/a.pdf">'
    assert pdf_url("pub.example", {"doi": "10.9/x"}, "https://pub.example/a", html) == "https://pub.example/a.pdf"


def test_challenge_titles_are_detected():
    assert CHALLENGE.search("Just a moment...") and CHALLENGE.search("Are you a robot?")
    assert not CHALLENGE.search("Collective motion of robots | IEEE Xplore")
