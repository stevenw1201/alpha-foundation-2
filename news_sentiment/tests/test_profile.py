"""Tests for tools/profile.py — validates parsing against the TSLA initiation file."""

from pathlib import Path

from news_sentiment.tools.profile import get_company_profile

# The data/ directory ships with the TSLA fixture and concept_map.json
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_returns_none_for_unknown_ticker():
    result = get_company_profile("ZZZZ", data_dir=DATA_DIR)
    assert result is None


def test_ticker_and_concept_uri():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    assert profile is not None
    assert profile["ticker"] == "TSLA"
    assert profile["concept_uri"] == "http://en.wikipedia.org/wiki/Tesla,_Inc."


# ---------------------------------------------------------------------------
# Level 1 — Sectors
# ---------------------------------------------------------------------------
def test_l1_sectors():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    sectors = profile["level_1"]["sectors"]
    assert len(sectors) == 2
    assert sectors[0] == {"name": "Consumer Discretionary", "score": 85}
    assert sectors[1] == {"name": "Industrials", "score": 55}


# ---------------------------------------------------------------------------
# Level 1 — Industries
# ---------------------------------------------------------------------------
def test_l1_industries():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    industries = profile["level_1"]["industries"]
    assert len(industries) == 3
    names = [i["name"] for i in industries]
    assert "Automobile Manufacturers" in names
    assert "Electrical Equipment (Energy Storage)" in names
    assert "Application Software (FSD/AI)" in names
    assert industries[0]["score"] == 90
    assert industries[1]["score"] == 75
    assert industries[2]["score"] == 60


# ---------------------------------------------------------------------------
# Level 1 — Trends
# ---------------------------------------------------------------------------
def test_l1_trends():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    trends = profile["level_1"]["trends"]
    assert len(trends) == 4
    expected = [
        {"name": "EV Adoption & Vehicle Electrification", "score": 95},
        {"name": "Autonomous Mobility", "score": 88},
        {"name": "AI Infrastructure Buildout", "score": 72},
        {"name": "Energy Transition & Grid Modernization", "score": 85},
    ]
    assert trends == expected


# ---------------------------------------------------------------------------
# Level 1 — Themes
# ---------------------------------------------------------------------------
def test_l1_themes():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    themes = profile["level_1"]["themes"]
    assert len(themes) == 4
    expected = [
        {"name": "Vertically Integrated EV Platforms", "score": 90},
        {"name": "Grid-Scale Battery Storage", "score": 82},
        {"name": "Robotics & Industrial Automation", "score": 65},
        {"name": "US-China Trade & Supply Chain Rebalancing", "score": 70},
    ]
    assert themes == expected


# ---------------------------------------------------------------------------
# Level 2 — Clusters
# ---------------------------------------------------------------------------
def test_l2_cluster_count():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    clusters = profile["level_2_clusters"]
    assert len(clusters) == 6


def test_l2_cluster_names_and_relevance():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    clusters = profile["level_2_clusters"]
    by_name = {c["name"]: c for c in clusters}

    assert by_name["Mobility & Transport"]["relevance"] == 92
    assert by_name["AI & Compute"]["relevance"] == 75
    assert by_name["Energy & Grid"]["relevance"] == 84
    assert by_name["Supply Chain & Trade"]["relevance"] == 70
    assert by_name["Consumer Demand"]["relevance"] == 65
    assert by_name["Regulatory & Policy"]["relevance"] == 68


def test_l2_cluster_member_tags():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    clusters = profile["level_2_clusters"]
    by_name = {c["name"]: c for c in clusters}

    assert by_name["Mobility & Transport"]["member_tags"] == [
        "EV Adoption & Vehicle Electrification",
        "Autonomous Mobility",
        "Vertically Integrated EV Platforms",
    ]
    assert by_name["AI & Compute"]["member_tags"] == [
        "AI Infrastructure Buildout",
        "Autonomous Mobility",
        "Robotics & Industrial Automation",
    ]
    assert by_name["Energy & Grid"]["member_tags"] == [
        "Energy Transition & Grid Modernization",
        "Grid-Scale Battery Storage",
    ]
    assert by_name["Supply Chain & Trade"]["member_tags"] == [
        "US-China Trade & Supply Chain Rebalancing",
        "EV Adoption & Vehicle Electrification",
    ]
    assert by_name["Consumer Demand"]["member_tags"] == [
        "Vertically Integrated EV Platforms",
        "EV Adoption & Vehicle Electrification",
    ]
    assert by_name["Regulatory & Policy"]["member_tags"] == [
        "Autonomous Mobility",
        "Energy Transition & Grid Modernization",
        "US-China Trade & Supply Chain Rebalancing",
    ]


# ---------------------------------------------------------------------------
# Full structure shape check
# ---------------------------------------------------------------------------
def test_full_profile_keys():
    profile = get_company_profile("TSLA", data_dir=DATA_DIR)
    assert set(profile.keys()) == {"ticker", "concept_uri", "level_1", "level_2_clusters"}
    assert set(profile["level_1"].keys()) == {"sectors", "industries", "trends", "themes"}
