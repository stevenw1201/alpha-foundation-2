"""Tests for agent.py — validates tool dispatch, scoring functions, and pipeline wiring."""

import json
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest

from news_sentiment.agent import (
    _execute_tool,
    _parse_json_array,
    _strip_article_metadata,
    run_agent,
    run_company_pipeline,
    run_macro_pipeline,
    score_company_articles,
    score_macro_events,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    MODEL,
    SCORING_MODEL,
    MACRO_SCORING_MODEL,
)

# ---------------------------------------------------------------------------
# System prompt & tool definition checks
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_contains_scoring_methodology(self):
        assert "SCORING METHODOLOGY:" in SYSTEM_PROMPT

    def test_contains_sentiment_direction_guidance(self):
        assert "directional impact on THIS COMPANY" in SYSTEM_PROMPT

    def test_contains_macro_schema(self):
        assert "cluster_impacts" in SYSTEM_PROMPT
        assert "event_type" in SYSTEM_PROMPT

    def test_contains_output_format(self):
        assert "store_scored_articles" in SYSTEM_PROMPT
        assert "store_macro_events" in SYSTEM_PROMPT


class TestToolDefinitions:
    def test_has_all_six_tools(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert names == {
            "get_company_profile",
            "fetch_company_news",
            "fetch_macro_news",
            "store_scored_articles",
            "store_macro_events",
            "compute_index",
        }

    def test_all_have_input_schema(self):
        for tool in TOOL_DEFINITIONS:
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "required" in tool["input_schema"]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

class TestExecuteTool:
    @patch("news_sentiment.agent.get_company_profile")
    def test_dispatch_get_company_profile(self, mock_fn):
        mock_fn.return_value = {"ticker": "TSLA", "concept_uri": "http://example.com"}
        result = json.loads(_execute_tool("get_company_profile", {"ticker": "TSLA"}))
        assert result["ticker"] == "TSLA"
        mock_fn.assert_called_once_with("TSLA")

    @patch("news_sentiment.agent.fetch_company_news")
    def test_dispatch_fetch_company_news(self, mock_fn):
        mock_fn.return_value = [{"uri": "a1", "title": "Test"}]
        result = json.loads(_execute_tool("fetch_company_news", {
            "concept_uri": "http://example.com",
            "from_date": "2026-03-12",
            "to_date": "2026-03-13",
        }))
        assert len(result) == 1
        mock_fn.assert_called_once()

    @patch("news_sentiment.agent.fetch_macro_news")
    def test_dispatch_fetch_macro_news(self, mock_fn):
        mock_fn.return_value = []
        result = json.loads(_execute_tool("fetch_macro_news", {
            "from_date": "2026-03-12",
            "to_date": "2026-03-13",
        }))
        assert result == []

    @patch("news_sentiment.agent.store_scored_articles")
    def test_dispatch_store_scored_articles(self, mock_fn):
        mock_fn.return_value = 3
        result = json.loads(_execute_tool("store_scored_articles", {
            "ticker": "TSLA",
            "articles": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}],
        }))
        assert result["stored"] == 3

    @patch("news_sentiment.agent.store_macro_events")
    def test_dispatch_store_macro_events(self, mock_fn):
        mock_fn.return_value = 2
        result = json.loads(_execute_tool("store_macro_events", {
            "events": [{"id": "m1"}, {"id": "m2"}],
        }))
        assert result["stored"] == 2

    @patch("news_sentiment.agent.compute_index")
    def test_dispatch_compute_index(self, mock_fn):
        mock_fn.return_value = {"ticker": "TSLA", "index_value": 0.15}
        result = json.loads(_execute_tool("compute_index", {
            "ticker": "TSLA",
            "as_of_date": "2026-03-13",
        }))
        assert result["index_value"] == 0.15

    def test_unknown_tool(self):
        result = json.loads(_execute_tool("nonexistent", {}))
        assert "error" in result


# ---------------------------------------------------------------------------
# Article metadata stripping
# ---------------------------------------------------------------------------

class TestStripArticleMetadata:
    def test_removes_categories_and_concepts(self):
        articles = [{
            "uri": "a1",
            "title": "Test headline",
            "source": {"uri": "reuters.com", "title": "Reuters"},
            "categories": [{"uri": "dmoz/Business", "wgt": 85}],
            "concepts": [{"uri": "http://en.wikipedia.org/wiki/Tesla", "type": "org"}],
        }]
        stripped = _strip_article_metadata(articles)
        assert "categories" not in stripped[0]
        assert "concepts" not in stripped[0]

    def test_preserves_scoring_fields(self):
        articles = [{
            "uri": "a1",
            "title": "Test headline",
            "url": "https://example.com",
            "dateTimePub": "2026-03-13T10:00:00Z",
            "source": {"uri": "reuters.com", "title": "Reuters"},
            "sentiment": 0.24,
            "eventUri": "eng-12345",
            "categories": [{"uri": "dmoz/Business", "wgt": 85}],
            "concepts": [{"uri": "http://en.wikipedia.org/wiki/Tesla", "type": "org"}],
        }]
        stripped = _strip_article_metadata(articles)
        art = stripped[0]
        assert art["uri"] == "a1"
        assert art["title"] == "Test headline"
        assert art["url"] == "https://example.com"
        assert art["source"]["uri"] == "reuters.com"
        assert art["sentiment"] == 0.24
        assert art["eventUri"] == "eng-12345"

    @patch("news_sentiment.agent.fetch_company_news")
    def test_dispatch_strips_metadata(self, mock_fn):
        """fetch_company_news dispatch strips categories/concepts."""
        mock_fn.return_value = [{
            "uri": "a1",
            "title": "News",
            "categories": [{"uri": "dmoz/Business", "wgt": 85}],
            "concepts": [{"uri": "http://en.wikipedia.org/wiki/X", "type": "org"}],
        }]
        result = json.loads(_execute_tool("fetch_company_news", {
            "concept_uri": "http://example.com",
            "from_date": "2026-03-12",
            "to_date": "2026-03-13",
        }))
        assert "categories" not in result[0]
        assert "concepts" not in result[0]
        assert result[0]["uri"] == "a1"


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

class TestParseJsonArray:
    def test_plain_json(self):
        result = _parse_json_array('[{"id": "a1"}]')
        assert result == [{"id": "a1"}]

    def test_with_code_fences(self):
        text = '```json\n[{"id": "a1"}]\n```'
        result = _parse_json_array(text)
        assert result == [{"id": "a1"}]

    def test_with_plain_fences(self):
        text = '```\n[{"id": "a1"}]\n```'
        result = _parse_json_array(text)
        assert result == [{"id": "a1"}]

    def test_with_whitespace(self):
        result = _parse_json_array('  \n[{"id": "a1"}]  \n')
        assert result == [{"id": "a1"}]

    def test_empty_array(self):
        assert _parse_json_array("[]") == []


# ---------------------------------------------------------------------------
# Agent loop (fully mocked Anthropic client — backward compat)
# ---------------------------------------------------------------------------

def _make_text_block(text):
    return SimpleNamespace(type="text", text=text)


def _make_tool_use_block(tool_id, name, input_dict):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=input_dict)


class TestAgentLoop:
    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_simple_text_response(self, MockClient):
        """Agent returns text on first turn with no tool calls."""
        mock_response = SimpleNamespace(
            content=[_make_text_block("Done. Index is +0.15.")],
            stop_reason="end_turn",
        )
        MockClient.return_value.messages.create.return_value = mock_response
        result = run_agent("test task")
        assert "Done" in result

    @patch("news_sentiment.agent.anthropic.Anthropic")
    @patch("news_sentiment.agent._execute_tool")
    def test_tool_call_then_text(self, mock_exec, MockClient):
        """Agent calls a tool, gets result, then produces final text."""
        # Turn 1: tool call
        tool_response = SimpleNamespace(
            content=[
                _make_tool_use_block("tu_1", "get_company_profile", {"ticker": "TSLA"}),
            ],
            stop_reason="tool_use",
        )
        # Turn 2: final text
        text_response = SimpleNamespace(
            content=[_make_text_block("Profile loaded. TSLA index: +0.15")],
            stop_reason="end_turn",
        )
        MockClient.return_value.messages.create.side_effect = [tool_response, text_response]
        mock_exec.return_value = '{"ticker": "TSLA"}'

        result = run_agent("Run company pipeline for TSLA")
        assert "TSLA" in result
        assert mock_exec.call_count == 1

    @patch("news_sentiment.agent.anthropic.Anthropic")
    @patch("news_sentiment.agent._execute_tool")
    def test_multi_tool_calls(self, mock_exec, MockClient):
        """Agent makes multiple tool calls across turns."""
        # Turn 1: get_company_profile
        turn1 = SimpleNamespace(
            content=[_make_tool_use_block("tu_1", "get_company_profile", {"ticker": "TSLA"})],
            stop_reason="tool_use",
        )
        # Turn 2: fetch_company_news
        turn2 = SimpleNamespace(
            content=[_make_tool_use_block("tu_2", "fetch_company_news", {
                "concept_uri": "http://x", "from_date": "2026-03-12", "to_date": "2026-03-13",
            })],
            stop_reason="tool_use",
        )
        # Turn 3: final text
        turn3 = SimpleNamespace(
            content=[_make_text_block("Scored 5 articles. Index: +0.07")],
            stop_reason="end_turn",
        )
        MockClient.return_value.messages.create.side_effect = [turn1, turn2, turn3]
        mock_exec.return_value = '[]'

        result = run_agent("Run pipeline")
        assert mock_exec.call_count == 2
        assert "Scored" in result

    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_max_turns_safety(self, MockClient):
        """Agent loop terminates after max_turns."""
        # Always return a tool call — should eventually hit the limit
        tool_response = SimpleNamespace(
            content=[_make_tool_use_block("tu_1", "get_company_profile", {"ticker": "TSLA"})],
            stop_reason="tool_use",
        )
        MockClient.return_value.messages.create.return_value = tool_response

        with patch("news_sentiment.agent._execute_tool", return_value='{}'):
            result = run_agent("loop forever", max_turns=3)
        assert "max turns" in result.lower()


# ---------------------------------------------------------------------------
# Single-call scoring functions
# ---------------------------------------------------------------------------

class TestModelDefaults:
    def test_scoring_model_is_haiku(self):
        assert "haiku" in SCORING_MODEL

    def test_macro_scoring_model_is_sonnet(self):
        assert "sonnet" in MACRO_SCORING_MODEL

    def test_model_is_sonnet(self):
        """Legacy MODEL constant remains Sonnet."""
        assert "sonnet" in MODEL


class TestScoreCompanyArticles:
    def test_empty_articles_returns_empty(self):
        """No API call needed for empty input."""
        result = score_company_articles("TSLA", {"ticker": "TSLA"}, [])
        assert result == []

    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_single_call_scoring(self, MockClient):
        """Verifies single API call produces scored articles."""
        scored_json = json.dumps([{
            "id": "a1", "ticker": "TSLA", "headline": "Tesla earnings beat",
            "source": "reuters.com", "url": "https://example.com",
            "published_at": "2026-03-13T10:00:00Z",
            "scored_at": "2026-03-13T15:00:00Z",
            "event_uri": None,
            "article_tags": ["earnings", "beat"],
            "sentiment": 0.6, "confidence": 0.85, "impact": 0.7,
            "tag_similarity": {"level_1_score": 0.8, "level_2_score": 0.7, "combined": 0.76},
            "final_score": 0.273,
        }])
        mock_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=scored_json)],
        )
        MockClient.return_value.messages.create.return_value = mock_response

        profile = {"ticker": "TSLA", "l1_tags": [], "l2_clusters": []}
        articles = [{"uri": "a1", "title": "Tesla earnings beat",
                     "source": {"uri": "reuters.com"}}]

        result = score_company_articles("TSLA", profile, articles)

        assert len(result) == 1
        assert result[0]["id"] == "a1"
        assert result[0]["sentiment"] == 0.6
        # Verify only ONE API call was made
        assert MockClient.return_value.messages.create.call_count == 1
        # Verify no tools were passed (single-call, no tool use)
        call_kwargs = MockClient.return_value.messages.create.call_args
        assert "tools" not in call_kwargs.kwargs

    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_uses_haiku_by_default(self, MockClient):
        """Company scoring defaults to Haiku for cost efficiency."""
        mock_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text='[{"id": "a1"}]')],
        )
        MockClient.return_value.messages.create.return_value = mock_response

        score_company_articles("TSLA", {"ticker": "TSLA"}, [{"uri": "a1", "title": "Test"}])

        call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
        assert call_kwargs["model"] == SCORING_MODEL
        assert "haiku" in call_kwargs["model"]

    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_handles_code_fences(self, MockClient):
        """Model output wrapped in markdown fences is handled."""
        scored_json = '```json\n[{"id": "a1", "sentiment": 0.5}]\n```'
        mock_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=scored_json)],
        )
        MockClient.return_value.messages.create.return_value = mock_response

        result = score_company_articles(
            "TSLA", {"ticker": "TSLA"}, [{"uri": "a1", "title": "Test"}],
        )
        assert result[0]["id"] == "a1"


class TestScoreMacroEvents:
    def test_empty_articles_returns_empty(self):
        result = score_macro_events([])
        assert result == []

    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_uses_sonnet_by_default(self, MockClient):
        """Macro scoring defaults to Sonnet for nuanced reasoning."""
        mock_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text='[{"id": "m1"}]')],
        )
        MockClient.return_value.messages.create.return_value = mock_response

        score_macro_events([{"uri": "m1", "title": "Fed holds"}])

        call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
        assert call_kwargs["model"] == MACRO_SCORING_MODEL
        assert "sonnet" in call_kwargs["model"]

    @patch("news_sentiment.agent.anthropic.Anthropic")
    def test_single_call_scoring(self, MockClient):
        """Verifies single API call produces scored macro events."""
        scored_json = json.dumps([{
            "id": "m1", "event_uri": "eng-123",
            "event_type": "monetary_policy",
            "headline": "Fed holds rates",
            "source": "wsj.com", "url": "https://example.com",
            "published_at": "2026-03-13T14:00:00Z",
            "scored_at": "2026-03-13T15:00:00Z",
            "sentiment_direction": -0.15,
            "confidence": 0.9, "impact": 0.85,
            "cluster_impacts": {
                "Mobility & Transport": -0.10,
                "AI & Compute": -0.15,
                "Energy & Grid": -0.05,
                "Supply Chain & Trade": 0.0,
                "Consumer Demand": -0.20,
                "Capital Markets & Rates": 0.60,
                "Regulatory & Policy": 0.10,
                "Healthcare & Biotech": 0.0,
            },
        }])
        mock_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=scored_json)],
        )
        MockClient.return_value.messages.create.return_value = mock_response

        articles = [{"uri": "m1", "title": "Fed holds rates",
                     "source": {"uri": "wsj.com"}, "eventUri": "eng-123"}]

        result = score_macro_events(articles)

        assert len(result) == 1
        assert result[0]["event_type"] == "monetary_policy"
        assert MockClient.return_value.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Pipeline wrappers (single-call approach)
# ---------------------------------------------------------------------------

class TestPipelineWrappers:
    @patch("news_sentiment.agent.compute_index")
    @patch("news_sentiment.agent.store_scored_articles")
    @patch("news_sentiment.agent.score_company_articles")
    @patch("news_sentiment.agent.fetch_company_news")
    @patch("news_sentiment.agent.get_company_profile")
    def test_company_pipeline_orchestration(
        self, mock_profile, mock_fetch, mock_score, mock_store, mock_index,
    ):
        """Company pipeline calls steps in order: profile → fetch → score → store → index."""
        mock_profile.return_value = {
            "ticker": "TSLA",
            "concept_uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.",
        }
        mock_fetch.return_value = [
            {"uri": "a1", "title": "Test", "source": {"uri": "reuters.com"}},
        ]
        mock_score.return_value = [{"id": "a1", "sentiment": 0.5}]
        mock_store.return_value = 1
        mock_index.return_value = {
            "ticker": "TSLA", "index_value": 0.15,
            "company_component": 0.20, "macro_component": -0.05,
            "article_count": 1, "macro_event_count": 0,
        }

        result = run_company_pipeline("TSLA", "2026-03-12", "2026-03-13")

        # Verify orchestration order
        mock_profile.assert_called_once_with("TSLA")
        mock_fetch.assert_called_once_with(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
        )
        mock_score.assert_called_once()
        mock_store.assert_called_once_with("TSLA", [{"id": "a1", "sentiment": 0.5}])
        mock_index.assert_called_once_with("TSLA", "2026-03-13")

        # Result contains summary
        assert "TSLA" in result
        assert "+0.1500" in result

    @patch("news_sentiment.agent.get_company_profile")
    def test_company_pipeline_missing_profile(self, mock_profile):
        """Pipeline returns early when profile is missing."""
        mock_profile.return_value = None
        result = run_company_pipeline("FAKE", "2026-03-12", "2026-03-13")
        assert "No profile" in result

    @patch("news_sentiment.agent.get_company_profile")
    def test_company_pipeline_no_concept_uri(self, mock_profile):
        """Pipeline returns early when profile lacks concept_uri."""
        mock_profile.return_value = {"ticker": "FAKE"}
        result = run_company_pipeline("FAKE", "2026-03-12", "2026-03-13")
        assert "no concept_uri" in result

    @patch("news_sentiment.agent.fetch_company_news")
    @patch("news_sentiment.agent.get_company_profile")
    def test_company_pipeline_no_articles(self, mock_profile, mock_fetch):
        """Pipeline returns early when no articles found."""
        mock_profile.return_value = {
            "ticker": "TSLA",
            "concept_uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.",
        }
        mock_fetch.return_value = []
        result = run_company_pipeline("TSLA", "2026-03-12", "2026-03-13")
        assert "No articles" in result

    @patch("news_sentiment.agent.store_macro_events")
    @patch("news_sentiment.agent.score_macro_events")
    @patch("news_sentiment.agent.fetch_macro_news")
    def test_macro_pipeline_orchestration(
        self, mock_fetch, mock_score, mock_store,
    ):
        """Macro pipeline calls steps in order: fetch → score → store."""
        mock_fetch.return_value = [
            {"uri": "m1", "title": "Fed holds", "source": {"uri": "wsj.com"}},
        ]
        mock_score.return_value = [{"id": "m1", "event_type": "monetary_policy"}]
        mock_store.return_value = 1

        result = run_macro_pipeline("2026-03-12", "2026-03-13")

        mock_fetch.assert_called_once()
        mock_score.assert_called_once()
        mock_store.assert_called_once_with([{"id": "m1", "event_type": "monetary_policy"}])
        assert "1 events" in result

    @patch("news_sentiment.agent.fetch_macro_news")
    def test_macro_pipeline_no_articles(self, mock_fetch):
        """Macro pipeline returns early when no articles found."""
        mock_fetch.return_value = []
        result = run_macro_pipeline("2026-03-12", "2026-03-13")
        assert "No macro articles" in result
