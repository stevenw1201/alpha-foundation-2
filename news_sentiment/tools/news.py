"""Fetch news from NewsAPI.ai (Event Registry) REST API.

Two functions:
- fetch_company_news — entity-disambiguated search via concept URI
- fetch_macro_news   — category-filtered search for macro/political news

Both return a normalised list of article dicts ready for the agent to score.
"""

from __future__ import annotations

from pathlib import Path

import requests
import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
_API_URL = "https://eventregistry.org/api/v1/article/getArticles"


def _load_config(config_path: Path | None = None) -> dict:
    config_path = config_path or _CONFIG_PATH
    with open(config_path) as f:
        return yaml.safe_load(f)


def fetch_company_news(
    concept_uri: str,
    from_date: str,
    to_date: str,
    *,
    max_articles: int = 100,
    config_path: Path | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Fetch entity-disambiguated company news via concept URI.

    Args:
        concept_uri: NewsAPI.ai concept URI (e.g.
            ``http://en.wikipedia.org/wiki/Tesla,_Inc.``).
        from_date: Start date inclusive, ``YYYY-MM-DD``.
        to_date: End date inclusive, ``YYYY-MM-DD``.
        max_articles: Maximum articles to return (default 100).
        config_path: Override path to config.yaml.
        api_key: Override API key (takes precedence over config).

    Returns:
        List of normalised article dicts.
    """
    cfg = _load_config(config_path)
    key = api_key or cfg["newsapi_key"]
    lang = cfg.get("default_lang", "eng")
    rank_pct = cfg.get("source_rank_percentile", [0, 80])

    body = {
        "apiKey": key,
        "resultType": "articles",
        "conceptUri": concept_uri,
        "lang": lang,
        "dateStart": from_date,
        "dateEnd": to_date,
        "isDuplicateFilter": "skipDuplicates",
        "includeArticleConcepts": True,
        "includeArticleCategories": True,
        "articlesSortBy": "date",
        "articlesCount": max_articles,
        "startSourceRankPercentile": rank_pct[0],
        "endSourceRankPercentile": rank_pct[1],
    }

    raw_articles = _call_api(body)
    return [_normalise_article(a) for a in raw_articles]


def fetch_macro_news(
    category_uris: list[str] | None = None,
    from_date: str = "",
    to_date: str = "",
    *,
    max_articles: int = 100,
    config_path: Path | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Fetch macro/political news filtered by category URIs.

    Args:
        category_uris: List of DMOZ / NewsAPI category URIs.  Falls back to
            ``macro_categories`` from config.yaml if not provided.
        from_date: Start date inclusive, ``YYYY-MM-DD``.
        to_date: End date inclusive, ``YYYY-MM-DD``.
        max_articles: Maximum articles to return (default 100).
        config_path: Override path to config.yaml.
        api_key: Override API key.

    Returns:
        List of normalised article dicts.
    """
    cfg = _load_config(config_path)
    key = api_key or cfg["newsapi_key"]
    lang = cfg.get("default_lang", "eng")
    rank_pct = cfg.get("source_rank_percentile", [0, 80])

    if category_uris is None:
        category_uris = cfg.get("macro_categories", [])

    body = {
        "apiKey": key,
        "resultType": "articles",
        "categoryUri": category_uris,
        "lang": lang,
        "dateStart": from_date,
        "dateEnd": to_date,
        "isDuplicateFilter": "skipDuplicates",
        "includeArticleConcepts": True,
        "includeArticleCategories": True,
        "articlesSortBy": "date",
        "articlesCount": max_articles,
        "startSourceRankPercentile": rank_pct[0],
        "endSourceRankPercentile": rank_pct[1],
    }

    raw_articles = _call_api(body)
    return [_normalise_article(a) for a in raw_articles]


# ---------------------------------------------------------------------------
# API plumbing
# ---------------------------------------------------------------------------

def _call_api(body: dict) -> list[dict]:
    """POST to the NewsAPI.ai article search endpoint and return raw articles."""
    resp = requests.post(
        _API_URL,
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    articles = data.get("articles", {})
    # The API nests results under articles.results
    return articles.get("results", [])


def _normalise_article(raw: dict) -> dict:
    """Map raw API response fields to our internal article schema."""
    source = raw.get("source", {})
    return {
        "uri": raw.get("uri", ""),
        "title": raw.get("title", ""),
        "url": raw.get("url", ""),
        "dateTimePub": raw.get("dateTimePub", ""),
        "source": {
            "uri": source.get("uri", ""),
            "title": source.get("title", ""),
        },
        "sentiment": raw.get("sentiment", None),
        "eventUri": raw.get("eventUri", None),
        "categories": [
            {"uri": c.get("uri", ""), "wgt": c.get("wgt", 0)}
            for c in raw.get("categories", [])
        ],
        "concepts": [
            {"uri": c.get("uri", ""), "type": c.get("type", "")}
            for c in raw.get("concepts", [])
        ],
    }
