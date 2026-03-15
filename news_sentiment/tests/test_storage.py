"""Tests for tools/storage.py — validates JSON persistence and idempotency."""

import json
from pathlib import Path

import pytest

from news_sentiment.tools.storage import store_scored_articles, store_macro_events


@pytest.fixture()
def tmp_data(tmp_path):
    """Provide a temporary data directory with the expected sub-structure."""
    (tmp_path / "articles").mkdir()
    (tmp_path / "macro").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------

def _article(id_: str = "art-1", published_at: str = "2026-03-13T10:00:00Z", **overrides):
    base = {
        "id": id_,
        "ticker": "TSLA",
        "headline": "Tesla news",
        "source": "reuters.com",
        "url": "https://example.com/1",
        "published_at": published_at,
        "scored_at": "2026-03-13T14:00:00Z",
        "event_uri": "eng-100",
        "article_tags": ["ev"],
        "sentiment": 0.5,
        "confidence": 0.8,
        "impact": 0.7,
        "tag_similarity": {"level_1_score": 0.8, "level_2_score": 0.9, "combined": 0.84},
        "final_score": 0.235,
    }
    base.update(overrides)
    return base


def _macro_event(id_: str = "macro-1", published_at: str = "2026-03-13T14:00:00Z", **overrides):
    base = {
        "id": id_,
        "event_uri": "eng-200",
        "event_type": "monetary_policy",
        "headline": "Fed holds rates",
        "source": "wsj.com",
        "url": "https://example.com/2",
        "published_at": published_at,
        "scored_at": "2026-03-13T15:00:00Z",
        "sentiment_direction": -0.30,
        "confidence": 0.85,
        "impact": 0.70,
        "cluster_impacts": {"Mobility & Transport": -0.15},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# store_scored_articles
# ---------------------------------------------------------------------------

class TestStoreArticles:
    def test_creates_file_and_writes(self, tmp_data):
        arts = [_article()]
        count = store_scored_articles("TSLA", arts, data_dir=tmp_data)
        assert count == 1
        path = tmp_data / "articles" / "TSLA" / "2026-03-13.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1
        assert data[0]["id"] == "art-1"

    def test_appends_new_article_to_existing_file(self, tmp_data):
        store_scored_articles("TSLA", [_article("a1")], data_dir=tmp_data)
        store_scored_articles("TSLA", [_article("a2")], data_dir=tmp_data)
        path = tmp_data / "articles" / "TSLA" / "2026-03-13.json"
        data = json.loads(path.read_text())
        assert len(data) == 2
        ids = {a["id"] for a in data}
        assert ids == {"a1", "a2"}

    def test_idempotent_on_id(self, tmp_data):
        store_scored_articles("TSLA", [_article("a1", sentiment=0.5)], data_dir=tmp_data)
        store_scored_articles("TSLA", [_article("a1", sentiment=-0.9)], data_dir=tmp_data)
        path = tmp_data / "articles" / "TSLA" / "2026-03-13.json"
        data = json.loads(path.read_text())
        assert len(data) == 1
        assert data[0]["sentiment"] == -0.9  # overwritten

    def test_groups_by_date(self, tmp_data):
        arts = [
            _article("a1", published_at="2026-03-12T08:00:00Z"),
            _article("a2", published_at="2026-03-13T10:00:00Z"),
        ]
        count = store_scored_articles("TSLA", arts, data_dir=tmp_data)
        assert count == 2
        assert (tmp_data / "articles" / "TSLA" / "2026-03-12.json").exists()
        assert (tmp_data / "articles" / "TSLA" / "2026-03-13.json").exists()

    def test_creates_ticker_directory(self, tmp_data):
        """Ticker subdirectory is auto-created if missing."""
        store_scored_articles("NVDA", [_article()], data_dir=tmp_data)
        assert (tmp_data / "articles" / "NVDA" / "2026-03-13.json").exists()

    def test_returns_count(self, tmp_data):
        arts = [_article("a1"), _article("a2"), _article("a3")]
        assert store_scored_articles("TSLA", arts, data_dir=tmp_data) == 3

    def test_empty_list_is_noop(self, tmp_data):
        assert store_scored_articles("TSLA", [], data_dir=tmp_data) == 0


# ---------------------------------------------------------------------------
# store_macro_events
# ---------------------------------------------------------------------------

class TestStoreMacroEvents:
    def test_creates_file_and_writes(self, tmp_data):
        count = store_macro_events([_macro_event()], data_dir=tmp_data)
        assert count == 1
        path = tmp_data / "macro" / "2026-03-13.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1

    def test_appends_new_events(self, tmp_data):
        store_macro_events([_macro_event("m1")], data_dir=tmp_data)
        store_macro_events([_macro_event("m2")], data_dir=tmp_data)
        path = tmp_data / "macro" / "2026-03-13.json"
        data = json.loads(path.read_text())
        assert len(data) == 2

    def test_idempotent_on_id(self, tmp_data):
        store_macro_events([_macro_event("m1", confidence=0.85)], data_dir=tmp_data)
        store_macro_events([_macro_event("m1", confidence=0.50)], data_dir=tmp_data)
        path = tmp_data / "macro" / "2026-03-13.json"
        data = json.loads(path.read_text())
        assert len(data) == 1
        assert data[0]["confidence"] == 0.50

    def test_groups_by_date(self, tmp_data):
        evts = [
            _macro_event("m1", published_at="2026-03-12T12:00:00Z"),
            _macro_event("m2", published_at="2026-03-13T14:00:00Z"),
        ]
        store_macro_events(evts, data_dir=tmp_data)
        assert (tmp_data / "macro" / "2026-03-12.json").exists()
        assert (tmp_data / "macro" / "2026-03-13.json").exists()

    def test_empty_list_is_noop(self, tmp_data):
        assert store_macro_events([], data_dir=tmp_data) == 0
