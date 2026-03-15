"""Tests for tools/news.py — mocked API calls to validate request building and response normalisation."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from news_sentiment.tools.news import fetch_company_news, fetch_macro_news

# Minimal config for tests
_TEST_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"

# A realistic API response fragment
_SAMPLE_API_RESPONSE = {
    "articles": {
        "results": [
            {
                "uri": "8277692764",
                "title": "Tesla Megapack powers new grid storage project",
                "body": "Tesla's energy division announced a major new Megapack deployment...",
                "url": "https://example.com/tesla-megapack",
                "dateTimePub": "2026-03-13T10:00:00Z",
                "source": {"uri": "reuters.com", "title": "Reuters"},
                "sentiment": 0.24,
                "eventUri": "eng-12345",
                "categories": [
                    {"uri": "dmoz/Business/Investing", "wgt": 85},
                    {"uri": "news/Business", "wgt": 70},
                ],
                "concepts": [
                    {"uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.", "type": "org"},
                    {"uri": "http://en.wikipedia.org/wiki/Megapack", "type": "wiki"},
                ],
            },
            {
                "uri": "8277700001",
                "title": "Fed holds rates steady, signals cuts unlikely before Q4",
                "body": "The Federal Reserve held interest rates unchanged...",
                "url": "https://example.com/fed-holds",
                "dateTimePub": "2026-03-13T14:00:00Z",
                "source": {"uri": "wsj.com", "title": "Wall Street Journal"},
                "sentiment": -0.15,
                "eventUri": "eng-67890",
                "categories": [
                    {"uri": "dmoz/Business/Financial_Services/Banking", "wgt": 95},
                ],
                "concepts": [
                    {"uri": "http://en.wikipedia.org/wiki/Federal_Reserve", "type": "org"},
                ],
            },
        ],
        "totalResults": 2,
        "page": 1,
        "count": 2,
        "pages": 1,
    }
}


def _mock_post(*args, **kwargs):
    """Return a mock response that behaves like requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _SAMPLE_API_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# fetch_company_news
# ---------------------------------------------------------------------------
class TestFetchCompanyNews:
    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_returns_normalised_articles(self, mock_post):
        articles = fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            config_path=_TEST_CONFIG,
        )
        assert len(articles) == 2
        art = articles[0]
        assert art["uri"] == "8277692764"
        assert art["title"] == "Tesla Megapack powers new grid storage project"
        assert art["source"] == {"uri": "reuters.com", "title": "Reuters"}
        assert art["eventUri"] == "eng-12345"
        assert art["sentiment"] == 0.24

    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_categories_normalised(self, mock_post):
        articles = fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            config_path=_TEST_CONFIG,
        )
        cats = articles[0]["categories"]
        assert len(cats) == 2
        assert cats[0] == {"uri": "dmoz/Business/Investing", "wgt": 85}

    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_concepts_normalised(self, mock_post):
        articles = fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            config_path=_TEST_CONFIG,
        )
        concepts = articles[0]["concepts"]
        assert len(concepts) == 2
        assert concepts[0]["uri"] == "http://en.wikipedia.org/wiki/Tesla,_Inc."
        assert concepts[0]["type"] == "org"

    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_request_body_has_correct_params(self, mock_post):
        fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            max_articles=50,
            config_path=_TEST_CONFIG,
        )
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["conceptUri"] == "http://en.wikipedia.org/wiki/Tesla,_Inc."
        assert body["dateStart"] == "2026-03-12"
        assert body["dateEnd"] == "2026-03-13"
        assert body["isDuplicateFilter"] == "skipDuplicates"
        assert body["lang"] == "eng"
        assert body["articlesSortBy"] == "date"
        assert body["articlesCount"] == 50
        assert body["includeArticleConcepts"] is True
        assert body["includeArticleCategories"] is True
        assert body["resultType"] == "articles"

    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_api_key_from_override(self, mock_post):
        fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            config_path=_TEST_CONFIG,
            api_key="override-key",
        )
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["apiKey"] == "override-key"


# ---------------------------------------------------------------------------
# fetch_macro_news
# ---------------------------------------------------------------------------
class TestFetchMacroNews:
    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_returns_normalised_articles(self, mock_post):
        articles = fetch_macro_news(
            from_date="2026-03-12", to_date="2026-03-13",
            config_path=_TEST_CONFIG,
        )
        assert len(articles) == 2
        art = articles[1]
        assert art["uri"] == "8277700001"
        assert art["source"]["uri"] == "wsj.com"

    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_uses_config_categories_by_default(self, mock_post):
        fetch_macro_news(
            from_date="2026-03-12", to_date="2026-03-13",
            config_path=_TEST_CONFIG,
        )
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        # Should use the macro_categories from config.yaml
        assert isinstance(body["categoryUri"], list)
        assert "dmoz/Business/Financial_Services/Banking" in body["categoryUri"]
        assert "news/Business" in body["categoryUri"]
        assert len(body["categoryUri"]) == 6

    @patch("news_sentiment.tools.news.requests.post", side_effect=_mock_post)
    def test_custom_category_uris(self, mock_post):
        custom = ["news/Economy", "dmoz/Society/Government"]
        fetch_macro_news(
            category_uris=custom,
            from_date="2026-03-12", to_date="2026-03-13",
            config_path=_TEST_CONFIG,
        )
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert body["categoryUri"] == custom


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    @patch("news_sentiment.tools.news.requests.post")
    def test_empty_results(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"articles": {"results": [], "totalResults": 0}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        articles = fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            config_path=_TEST_CONFIG,
        )
        assert articles == []

    @patch("news_sentiment.tools.news.requests.post")
    def test_missing_optional_fields_normalised(self, mock_post):
        """Articles with missing optional fields get safe defaults."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "articles": {
                "results": [{
                    "uri": "minimal-article",
                    "title": "Minimal",
                }]
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        articles = fetch_company_news(
            "http://en.wikipedia.org/wiki/Tesla,_Inc.",
            "2026-03-12", "2026-03-13",
            config_path=_TEST_CONFIG,
        )
        art = articles[0]
        assert art["uri"] == "minimal-article"
        assert "body" not in art
        assert art["url"] == ""
        assert art["sentiment"] is None
        assert art["eventUri"] is None
        assert art["categories"] == []
        assert art["concepts"] == []
        assert art["source"] == {"uri": "", "title": ""}

    @patch("news_sentiment.tools.news.requests.post")
    def test_api_error_raises(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_post.return_value = mock_resp

        with pytest.raises(Exception, match="401"):
            fetch_company_news(
                "http://en.wikipedia.org/wiki/Tesla,_Inc.",
                "2026-03-12", "2026-03-13",
                config_path=_TEST_CONFIG,
            )
