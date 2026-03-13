"""Tests for tools/index.py — validates decay math with known inputs."""

import math
from datetime import date

from news_sentiment.tools.index import compute_index, decayed_weight

LAMBDA = 0.231

# A minimal TSLA-like profile for testing
PROFILE = {
    "ticker": "TSLA",
    "concept_uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.",
    "level_1": {
        "sectors": [{"name": "Consumer Discretionary", "score": 85}],
        "industries": [{"name": "Automobile Manufacturers", "score": 90}],
        "trends": [{"name": "EV Adoption & Vehicle Electrification", "score": 95}],
        "themes": [{"name": "Vertically Integrated EV Platforms", "score": 90}],
    },
    "level_2_clusters": [
        {
            "name": "Mobility & Transport",
            "relevance": 92,
            "member_tags": ["EV Adoption & Vehicle Electrification"],
        },
        {
            "name": "AI & Compute",
            "relevance": 75,
            "member_tags": ["AI Infrastructure Buildout"],
        },
        {
            "name": "Energy & Grid",
            "relevance": 84,
            "member_tags": ["Energy Transition & Grid Modernization"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Decay formula unit tests
# ---------------------------------------------------------------------------
class TestDecayFormula:
    def test_zero_days_returns_one(self):
        """No elapsed time → weight = 1.0 regardless of impact."""
        assert decayed_weight(LAMBDA, 0, 1.0) == 1.0
        assert decayed_weight(LAMBDA, 0, 0.5) == 1.0

    def test_half_life_at_impact_one(self):
        """At impact=1.0, half-life should be ~3 days (ln(2)/0.231 ≈ 3.0)."""
        half_life = math.log(2) / LAMBDA
        w = decayed_weight(LAMBDA, half_life, 1.0)
        assert abs(w - 0.5) < 1e-9

    def test_higher_impact_slower_decay(self):
        """Higher impact → slower decay (impact in denominator)."""
        w_low = decayed_weight(LAMBDA, 3, 0.5)
        w_high = decayed_weight(LAMBDA, 3, 1.0)
        assert w_high > w_low

    def test_impact_doubles_effective_half_life(self):
        """At impact=2.0, effective half-life should be ~6 days."""
        half_life_2 = math.log(2) / LAMBDA * 2.0
        w = decayed_weight(LAMBDA, half_life_2, 2.0)
        assert abs(w - 0.5) < 1e-9

    def test_zero_impact_returns_zero(self):
        assert decayed_weight(LAMBDA, 3, 0.0) == 0.0

    def test_negative_impact_returns_zero(self):
        assert decayed_weight(LAMBDA, 3, -1.0) == 0.0

    def test_14_day_old_low_impact_nearly_zero(self):
        """14-day-old article with impact=0.3 should have negligible weight."""
        w = decayed_weight(LAMBDA, 14, 0.3)
        assert w < 0.01


# ---------------------------------------------------------------------------
# Company-specific component
# ---------------------------------------------------------------------------
class TestCompanyComponent:
    def test_single_article_same_day(self):
        """Same-day article: weight=1.0, contribution = final_score."""
        articles = [{
            "headline": "Tesla Megapack deal",
            "published_at": "2026-03-13",
            "confidence": 0.8,
            "impact": 0.7,
            "final_score": 0.25,
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=articles, macro_events=[],
        )
        assert result["article_count"] == 1
        assert abs(result["company_component"] - 0.25) < 1e-9
        assert result["macro_component"] == 0.0
        assert abs(result["index_value"] - 0.25) < 1e-9

    def test_article_with_decay(self):
        """3-day-old article with impact=1.0 → weight ≈ 0.5."""
        articles = [{
            "headline": "Old news",
            "published_at": "2026-03-10",
            "confidence": 0.8,
            "impact": 1.0,
            "final_score": 0.40,
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=articles, macro_events=[],
        )
        expected_weight = math.exp(-LAMBDA * 3 / 1.0)
        expected = 0.40 * expected_weight
        assert abs(result["company_component"] - expected) < 1e-9

    def test_multiple_articles_sum(self):
        """Multiple articles: contributions should sum."""
        articles = [
            {
                "headline": "A",
                "published_at": "2026-03-13",
                "confidence": 0.9,
                "impact": 0.8,
                "final_score": 0.30,
            },
            {
                "headline": "B",
                "published_at": "2026-03-12",
                "confidence": 0.7,
                "impact": 0.5,
                "final_score": -0.20,
            },
        ]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=articles, macro_events=[],
        )
        w_a = math.exp(-LAMBDA * 0 / 0.8)  # 1.0
        w_b = math.exp(-LAMBDA * 1 / 0.5)
        expected = 0.30 * w_a + (-0.20) * w_b
        assert abs(result["company_component"] - expected) < 1e-9
        assert result["article_count"] == 2

    def test_confidence_floor_excludes_article(self):
        """Articles below confidence_floor (0.3) are excluded."""
        articles = [{
            "headline": "Low confidence",
            "published_at": "2026-03-13",
            "confidence": 0.2,
            "impact": 0.8,
            "final_score": 0.50,
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=articles, macro_events=[],
        )
        assert result["article_count"] == 0
        assert result["company_component"] == 0.0

    def test_lookback_cutoff(self):
        """Articles older than lookback_days are excluded."""
        articles = [{
            "headline": "Ancient news",
            "published_at": "2026-02-20",
            "confidence": 0.9,
            "impact": 1.0,
            "final_score": 0.50,
        }]
        result = compute_index(
            "TSLA", "2026-03-13", lookback_days=14,
            profile=PROFILE, articles=articles, macro_events=[],
        )
        assert result["article_count"] == 0

    def test_article_at_lookback_boundary_included(self):
        """Article exactly at lookback_days boundary is included."""
        articles = [{
            "headline": "Boundary article",
            "published_at": "2026-02-27",
            "confidence": 0.8,
            "impact": 0.5,
            "final_score": 0.10,
        }]
        result = compute_index(
            "TSLA", "2026-03-13", lookback_days=14,
            profile=PROFILE, articles=articles, macro_events=[],
        )
        assert result["article_count"] == 1


# ---------------------------------------------------------------------------
# Macro component
# ---------------------------------------------------------------------------
class TestMacroComponent:
    def test_single_macro_event_matching_clusters(self):
        """Macro event with cluster impacts propagated through profile."""
        macro_events = [{
            "headline": "Fed holds rates steady",
            "published_at": "2026-03-13",
            "confidence": 0.85,
            "impact": 0.70,
            "cluster_impacts": {
                "Mobility & Transport": -0.15,
                "AI & Compute": -0.20,
                "Energy & Grid": -0.10,
                # This cluster is NOT in the profile — should contribute 0
                "Capital Markets & Rates": 0.60,
            },
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=[], macro_events=macro_events,
        )
        # Same-day → weight = 1.0
        # cluster_sum = (-0.15 * 92/100) + (-0.20 * 75/100) + (-0.10 * 84/100)
        #             = -0.138 + -0.15 + -0.084 = -0.372
        # contribution = -0.372 * 0.85 * 1.0 = -0.3162
        cluster_sum = (-0.15 * 0.92) + (-0.20 * 0.75) + (-0.10 * 0.84)
        expected = cluster_sum * 0.85
        assert abs(result["macro_component"] - expected) < 1e-9
        assert result["macro_event_count"] == 1

    def test_macro_event_no_matching_clusters(self):
        """Macro event whose clusters don't match the profile → zero contribution."""
        macro_events = [{
            "headline": "Healthcare regulation",
            "published_at": "2026-03-13",
            "confidence": 0.90,
            "impact": 0.80,
            "cluster_impacts": {
                "Healthcare & Biotech": -0.50,
                "Capital Markets & Rates": 0.30,
            },
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=[], macro_events=macro_events,
        )
        # No matching clusters → contribution is 0, but event still counted
        assert result["macro_component"] == 0.0
        assert result["macro_event_count"] == 1

    def test_macro_event_with_decay(self):
        """2-day-old macro event with impact=0.7."""
        macro_events = [{
            "headline": "Tariff news",
            "published_at": "2026-03-11",
            "confidence": 0.80,
            "impact": 0.70,
            "cluster_impacts": {
                "Mobility & Transport": -0.30,
            },
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=[], macro_events=macro_events,
        )
        weight = math.exp(-LAMBDA * 2 / 0.70)
        cluster_sum = -0.30 * 0.92
        expected = cluster_sum * 0.80 * weight
        assert abs(result["macro_component"] - expected) < 1e-9

    def test_macro_below_confidence_floor_excluded(self):
        macro_events = [{
            "headline": "Low confidence macro",
            "published_at": "2026-03-13",
            "confidence": 0.1,
            "impact": 0.8,
            "cluster_impacts": {"Mobility & Transport": -0.50},
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=[], macro_events=macro_events,
        )
        assert result["macro_event_count"] == 0
        assert result["macro_component"] == 0.0


# ---------------------------------------------------------------------------
# Combined index
# ---------------------------------------------------------------------------
class TestCombinedIndex:
    def test_company_plus_macro(self):
        """index_value = company_component + macro_component."""
        articles = [{
            "headline": "Good TSLA news",
            "published_at": "2026-03-13",
            "confidence": 0.9,
            "impact": 0.8,
            "final_score": 0.30,
        }]
        macro_events = [{
            "headline": "Bad macro",
            "published_at": "2026-03-13",
            "confidence": 0.85,
            "impact": 0.70,
            "cluster_impacts": {"Mobility & Transport": -0.40},
        }]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=articles, macro_events=macro_events,
        )
        company = 0.30  # same day, weight=1
        macro = -0.40 * 0.92 * 0.85  # cluster_sum * confidence * weight(=1)
        assert abs(result["company_component"] - company) < 1e-9
        assert abs(result["macro_component"] - macro) < 1e-9
        assert abs(result["index_value"] - (company + macro)) < 1e-9


# ---------------------------------------------------------------------------
# Top contributors & output structure
# ---------------------------------------------------------------------------
class TestOutputStructure:
    def test_top_contributors_sorted_by_abs_contribution(self):
        articles = [
            {"headline": "Small", "published_at": "2026-03-13",
             "confidence": 0.8, "impact": 0.5, "final_score": 0.05},
            {"headline": "Big negative", "published_at": "2026-03-13",
             "confidence": 0.8, "impact": 0.5, "final_score": -0.50},
            {"headline": "Medium", "published_at": "2026-03-13",
             "confidence": 0.8, "impact": 0.5, "final_score": 0.20},
        ]
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=articles, macro_events=[],
        )
        headlines = [c["headline"] for c in result["top_company_contributors"]]
        assert headlines == ["Big negative", "Medium", "Small"]

    def test_empty_inputs_returns_zero(self):
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=[], macro_events=[],
        )
        assert result["index_value"] == 0.0
        assert result["article_count"] == 0
        assert result["macro_event_count"] == 0

    def test_result_keys(self):
        result = compute_index(
            "TSLA", "2026-03-13",
            profile=PROFILE, articles=[], macro_events=[],
        )
        expected_keys = {
            "ticker", "as_of_date", "index_value",
            "company_component", "macro_component",
            "article_count", "macro_event_count",
            "top_company_contributors", "top_macro_contributors",
            "index_history",
        }
        assert set(result.keys()) == expected_keys
        assert result["as_of_date"] == "2026-03-13"

    def test_no_profile_returns_empty(self):
        """Missing profile → zeroed result."""
        result = compute_index(
            "ZZZZ", "2026-03-13",
            profile=None, articles=[], macro_events=[],
        )
        assert result["index_value"] == 0.0
