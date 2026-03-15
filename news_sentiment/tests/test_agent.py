"""Tests for agent.py — validates tool dispatch, pipeline wiring, and agent loop with mocks."""

import json
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest

from news_sentiment.agent import (
    _execute_tool,
    run_agent,
    run_company_pipeline,
    run_macro_pipeline,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
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
# Agent loop (fully mocked Anthropic client)
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
# Pipeline wrappers
# ---------------------------------------------------------------------------

class TestPipelineWrappers:
    @patch("news_sentiment.agent.run_agent")
    def test_company_pipeline_formats_task(self, mock_run):
        mock_run.return_value = "done"
        run_company_pipeline("TSLA", "2026-03-12", "2026-03-13")
        task = mock_run.call_args[0][0]
        assert "COMPANY-SPECIFIC" in task
        assert "TSLA" in task
        assert "2026-03-12" in task
        assert "compute_index" in task

    @patch("news_sentiment.agent.run_agent")
    def test_macro_pipeline_formats_task(self, mock_run):
        mock_run.return_value = "done"
        run_macro_pipeline("2026-03-12", "2026-03-13")
        task = mock_run.call_args[0][0]
        assert "MACRO" in task
        assert "fetch_macro_news" in task
        assert "store_macro_events" in task
