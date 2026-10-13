from amlr.fulltext.manual import best_title_match, title_region, title_score

HOU = ("Chinese Physics B PAPER Disorder-to-order transition induced by spontaneous cooling regulation in robotic "
       "active matter To cite this article: Shuaixu Hou et al 2024 Chinese Phys. B 33 078701 View the article online "
       "You may also like Cluster analysis of collective behavior for a robotic swarm ")
SPRINGER = {"id": "a", "title": "Cluster Analysis of Collective Behavior for a Robotic Swarm"}
HOU_REC = {"id": "b", "title": "Disorder-to-order transition induced by spontaneous cooling regulation in robotic active matter"}


def test_title_region_stops_before_iop_related_articles():
    assert "Cluster" not in title_region(HOU)
    assert title_score(SPRINGER["title"], HOU) < 0.9
    assert best_title_match(HOU, [SPRINGER, HOU_REC])["id"] == "b"
    assert best_title_match(HOU, [SPRINGER]) is None


def test_title_region_ignores_generic_words_later_on_the_page():
    page = "Physical Review Letters Emergent field-driven robot swarm states " + "filler " * 60 + \
           "cluster analysis of the collective behavior of a robotic swarm"
    assert title_score(SPRINGER["title"], page) < 0.9
