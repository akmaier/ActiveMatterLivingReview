from amlr.fetch import crossref_subqueries
from amlr.search import SYNTAX, load_concepts, matches, render

C = load_concepts()


def test_local_matcher_follows_boolean_logic():
    assert matches(C, "Boundaries control collective dynamics of inertial self-propelled robots")
    assert matches(C, "Swarming, swirling and stasis in sequestered bristle-bots: self-propelled")
    assert matches(C, "Feedback control of Janus particles with light")
    assert matches(C, "Robophysics of locomotion")
    assert not matches(C, "A single robot arm grasps objects")
    assert not matches(C, "Active matter in bacterial suspensions")
    # Spelling variants and plurals are matched; truncation works on the last word only.
    assert matches(C, "Collective behaviour of kilobots")
    assert matches(C, "order parameters of a hexbug swarm")


def test_renderers_respect_source_truncation_rules():
    oa = render(C, SYNTAX["openalex"])
    assert "*" not in oa  # OpenAlex has no truncation operator
    pm = render(C, SYNTAX["pubmed"])
    assert '"active particle*"[tiab]' in pm  # PubMed truncates inside phrases
    ax = render(C, SYNTAX["arxiv"])
    assert "ti:robot*" in ax and 'ti:"active particle"' in ax


def test_crossref_subqueries_cover_pairs_and_phrases():
    sq = crossref_subqueries(C)
    n = len(C["active_matter"]) * len(C["robotic_agents"]) + len(C["colloids"]) * len(C["control"])
    assert len(sq) == n + len(C["composite_phrases"])
    assert "robotic active matter" in sq
