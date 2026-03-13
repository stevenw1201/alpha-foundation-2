"""Compute the daily sentiment index with exponential time-decay weighting."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Default from config — half-life ~3 days at impact=1.0
DEFAULT_LAMBDA = 0.231
DEFAULT_LOOKBACK = 14
CONFIDENCE_FLOOR = 0.3


def compute_index(
    ticker: str,
    as_of_date: date | str,
    lookback_days: int = DEFAULT_LOOKBACK,
    decay_lambda: float = DEFAULT_LAMBDA,
    *,
    profile: dict | None = None,
    articles: list[dict] | None = None,
    macro_events: list[dict] | None = None,
    data_dir: Path | None = None,
) -> dict:
    """Compute the decayed, aggregated daily sentiment index for *ticker*.

    Data can be injected directly (for testing) or read from disk.

    Args:
        ticker: Uppercase stock ticker.
        as_of_date: The date to compute the index for (ISO string or date).
        lookback_days: Hard cutoff — articles older than this are excluded.
        decay_lambda: Exponential decay rate.
        profile: Company profile dict (from get_company_profile). Loaded from
            disk if not provided.
        articles: Pre-loaded scored articles. Read from data/articles/ if None.
        macro_events: Pre-loaded macro events. Read from data/macro/ if None.
        data_dir: Override data directory.

    Returns:
        Index result dict with company/macro decomposition and top contributors.
    """
    if isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(as_of_date)

    data_dir = Path(data_dir) if data_dir else _DATA_DIR

    # --- Load profile if not injected ---
    if profile is None:
        from news_sentiment.tools.profile import get_company_profile
        profile = get_company_profile(ticker, data_dir=data_dir)
    if profile is None:
        return _empty_result(ticker, as_of_date)

    # Build cluster relevance lookup from profile
    cluster_relevance = {
        c["name"]: c["relevance"] for c in profile.get("level_2_clusters", [])
    }

    # --- Load articles if not injected ---
    if articles is None:
        articles = _load_articles(ticker, as_of_date, lookback_days, data_dir)

    # --- Load macro events if not injected ---
    if macro_events is None:
        macro_events = _load_macro_events(as_of_date, lookback_days, data_dir)

    # --- Company-specific component ---
    company_contributions: list[dict] = []
    for art in articles:
        days = _days_elapsed(as_of_date, art["published_at"])
        if days < 0 or days > lookback_days:
            continue
        confidence = art.get("confidence", 0)
        if confidence < CONFIDENCE_FLOOR:
            continue
        impact = art.get("impact", 0)
        if impact <= 0:
            continue
        final_score = art.get("final_score", 0)
        weight = math.exp(-decay_lambda * days / impact)
        contribution = final_score * weight
        company_contributions.append({
            "headline": art.get("headline", ""),
            "contribution": contribution,
            "days_old": days,
        })

    company_sentiment = sum(c["contribution"] for c in company_contributions)

    # --- Macro component ---
    macro_contributions: list[dict] = []
    for evt in macro_events:
        days = _days_elapsed(as_of_date, evt["published_at"])
        if days < 0 or days > lookback_days:
            continue
        confidence = evt.get("confidence", 0)
        if confidence < CONFIDENCE_FLOOR:
            continue
        impact = evt.get("impact", 0)
        if impact <= 0:
            continue
        weight = math.exp(-decay_lambda * days / impact)

        cluster_impacts = evt.get("cluster_impacts", {})
        cluster_sum = 0.0
        for cluster_name, cluster_impact in cluster_impacts.items():
            if cluster_name in cluster_relevance:
                cluster_sum += cluster_impact * (cluster_relevance[cluster_name] / 100)

        contribution = cluster_sum * confidence * weight
        macro_contributions.append({
            "headline": evt.get("headline", ""),
            "contribution": contribution,
            "days_old": days,
        })

    macro_sentiment = sum(c["contribution"] for c in macro_contributions)

    # --- Top contributors (sorted by absolute contribution, descending) ---
    top_company = sorted(
        company_contributions, key=lambda c: abs(c["contribution"]), reverse=True
    )[:5]
    top_macro = sorted(
        macro_contributions, key=lambda c: abs(c["contribution"]), reverse=True
    )[:5]

    return {
        "ticker": ticker,
        "as_of_date": as_of_date.isoformat(),
        "index_value": company_sentiment + macro_sentiment,
        "company_component": company_sentiment,
        "macro_component": macro_sentiment,
        "article_count": len(company_contributions),
        "macro_event_count": len(macro_contributions),
        "top_company_contributors": top_company,
        "top_macro_contributors": top_macro,
        "index_history": [],  # populated by caller when rolling history exists
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decayed_weight(decay_lambda: float, days_elapsed: float, impact: float) -> float:
    """Compute exp(-lambda * days_elapsed / impact).

    Exposed as a public helper for unit-testing the decay formula directly.
    """
    if impact <= 0:
        return 0.0
    return math.exp(-decay_lambda * days_elapsed / impact)


def _days_elapsed(as_of: date, published_at: str | date) -> float:
    """Return whole-day difference between *as_of* and *published_at*."""
    if isinstance(published_at, str):
        # Handle both "2026-03-13" and "2026-03-13T10:00:00Z"
        pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
    else:
        pub_date = published_at
    return (as_of - pub_date).days


def _empty_result(ticker: str, as_of_date: date) -> dict:
    return {
        "ticker": ticker,
        "as_of_date": as_of_date.isoformat(),
        "index_value": 0.0,
        "company_component": 0.0,
        "macro_component": 0.0,
        "article_count": 0,
        "macro_event_count": 0,
        "top_company_contributors": [],
        "top_macro_contributors": [],
        "index_history": [],
    }


def _load_articles(
    ticker: str, as_of: date, lookback_days: int, data_dir: Path
) -> list[dict]:
    """Read scored article JSON files from data/articles/{TICKER}/."""
    articles_dir = data_dir / "articles" / ticker
    if not articles_dir.exists():
        return []
    results = []
    start_date = as_of - timedelta(days=lookback_days)
    for day_offset in range(lookback_days + 1):
        d = start_date + timedelta(days=day_offset)
        path = articles_dir / f"{d.isoformat()}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
    return results


def _load_macro_events(
    as_of: date, lookback_days: int, data_dir: Path
) -> list[dict]:
    """Read macro event JSON files from data/macro/."""
    macro_dir = data_dir / "macro"
    if not macro_dir.exists():
        return []
    results = []
    start_date = as_of - timedelta(days=lookback_days)
    for day_offset in range(lookback_days + 1):
        d = start_date + timedelta(days=day_offset)
        path = macro_dir / f"{d.isoformat()}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
    return results
