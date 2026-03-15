"""Sentiment scoring — single-call approach for company and macro pipelines.

Replaces the multi-turn agentic loop with direct Python orchestration and
a single Claude API call for the scoring step only.  This eliminates the
duplicated output tokens (score once → store once) and the multi-turn context
accumulation overhead.

The old ``run_agent`` loop is preserved for backward compatibility but is no
longer used by the pipeline functions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from news_sentiment.tools.news import fetch_company_news, fetch_macro_news
from news_sentiment.tools.profile import get_company_profile
from news_sentiment.tools.storage import store_scored_articles, store_macro_events
from news_sentiment.tools.index import compute_index

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TURNS = 25

# ---------------------------------------------------------------------------
# System prompt  (kept for backward compat & reference — used by run_agent)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a financial news sentiment agent.  Your job is to ingest news articles,
score them against a company's tag profile, and produce structured data that
feeds a daily sentiment index.

You have access to tools for fetching news, loading company profiles, storing
scored articles and macro events, and computing the sentiment index.

When the user gives you a task (company pipeline or macro pipeline), execute
the workflow by calling the appropriate tools in sequence.

IMPORTANT WORKFLOW RULES:
- Always load the company profile FIRST — you need the tags and concept URI.
- If get_company_profile returns null, STOP and report the missing profile.
- Use the concept_uri from the profile for fetch_company_news.
- After fetching articles, SCORE THEM before calling store_scored_articles.
- For macro events, score them before calling store_macro_events.
- After storing, call compute_index to get the daily sentiment reading.
- End with a brief natural-language summary of the index result.

FILTERING RULES:
- Drop articles that are clearly tangential (company mentioned but not the subject).
- Use eventUri to deduplicate — if multiple articles share the same eventUri,
  keep only the highest-quality source (prefer Reuters, WSJ, Bloomberg, FT).
- Articles are fetched as headlines only (no body text). Score based on the
  headline, source, and metadata.

SCORING METHODOLOGY:
When you receive articles to score, output a JSON array. For each article:
1. article_tags: 2-5 free-form descriptive tags for what this article covers
2. sentiment: [-1, +1] — directional impact on THIS COMPANY, not article tone
   - "Competitor bankruptcy" = positive for this company even though the article is negative
   - "Analyst upgrades price target" = positive
   - "NHTSA opens investigation" = negative
   - "Routine quarterly update, in-line" = near zero
3. confidence: [0, 1] — how certain you are in the sentiment call
   - Low (< 0.5): ambiguous article, tangential mention, paywalled stub
   - High (> 0.8): clear directional event directly about the company
4. impact: [0, 1] — materiality to fundamentals or stock price
   - 0.8-1.0: CEO change, major M&A, earnings miss/beat, regulatory ruling
   - 0.5-0.7: product launch, guidance change, significant partnership
   - 0.2-0.4: analyst note, routine coverage, minor update
   - < 0.2: tangential mention, not investment-relevant
5. tag_similarity: assess overlap between your article_tags and the company profile
   - level_1_score: [0, 1] — how well article tags map to L1 Trends/Themes
   - level_2_score: [0, 1] — how well they map to L2 cluster domains
   - combined: level_1_score × 0.6 + level_2_score × 0.4
6. final_score: sentiment × confidence × impact × combined_similarity

For MACRO events, output a different schema:
1. event_type: monetary_policy | fiscal_policy | trade_policy | geopolitical | regulatory | economic_data | political | other
2. sentiment_direction: [-1, +1] overall market direction
3. confidence: [0, 1]
4. impact: [0, 1]
5. cluster_impacts: directional impact [-1, +1] for each standard cluster. Think about TRANSMISSION MECHANISMS — the same event affects different sectors differently:
   - Rate hike: Capital Markets & Rates positive (banks), Consumer Demand negative (borrowing costs)
   - Tariffs on China: Supply Chain & Trade negative, domestic Manufacturing positive

OUTPUT FORMAT for store_scored_articles — each article dict MUST have:
{
  "id": "<article uri>",
  "ticker": "<TICKER>",
  "headline": "<title>",
  "source": "<source uri>",
  "url": "<article url>",
  "published_at": "<dateTimePub>",
  "scored_at": "<current ISO timestamp>",
  "event_uri": "<eventUri or null>",
  "article_tags": ["tag1", "tag2", ...],
  "sentiment": <float>,
  "confidence": <float>,
  "impact": <float>,
  "tag_similarity": {
    "level_1_score": <float>,
    "level_2_score": <float>,
    "combined": <float>
  },
  "final_score": <float>
}

OUTPUT FORMAT for store_macro_events — each event dict MUST have:
{
  "id": "<article uri>",
  "event_uri": "<eventUri or null>",
  "event_type": "<type>",
  "headline": "<title>",
  "source": "<source uri>",
  "url": "<article url>",
  "published_at": "<dateTimePub>",
  "scored_at": "<current ISO timestamp>",
  "sentiment_direction": <float>,
  "confidence": <float>,
  "impact": <float>,
  "cluster_impacts": {
    "Mobility & Transport": <float>,
    "AI & Compute": <float>,
    "Energy & Grid": <float>,
    "Supply Chain & Trade": <float>,
    "Consumer Demand": <float>,
    "Capital Markets & Rates": <float>,
    "Regulatory & Policy": <float>,
    "Healthcare & Biotech": <float>
  }
}
Set cluster_impacts to 0.0 for clusters not meaningfully affected by the event.
"""

# ---------------------------------------------------------------------------
# Tool definitions (Claude tool_use format — kept for run_agent backward compat)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "get_company_profile",
        "description": (
            "Load a company's tag profile from the research agent's initiation "
            "report. Returns structured L1 tags (sectors, industries, trends, "
            "themes with scores) and L2 theme clusters (name, relevance, "
            "member_tags), plus the NewsAPI.ai concept URI. Returns null if "
            "no profile exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Uppercase stock ticker, e.g. TSLA",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "fetch_company_news",
        "description": (
            "Fetch entity-disambiguated company news from NewsAPI.ai using a "
            "concept URI. Returns deduplicated articles sorted by date with "
            "enriched metadata (concepts, categories). Use the concept_uri "
            "from get_company_profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "concept_uri": {
                    "type": "string",
                    "description": "NewsAPI.ai concept URI, e.g. http://en.wikipedia.org/wiki/Tesla,_Inc.",
                },
                "from_date": {
                    "type": "string",
                    "description": "Start date inclusive, YYYY-MM-DD",
                },
                "to_date": {
                    "type": "string",
                    "description": "End date inclusive, YYYY-MM-DD",
                },
            },
            "required": ["concept_uri", "from_date", "to_date"],
        },
    },
    {
        "name": "fetch_macro_news",
        "description": (
            "Fetch macro/political news from NewsAPI.ai filtered by category "
            "URIs. Returns deduplicated articles. Used for the macro pipeline — "
            "these articles are scored once with a cluster impact vector, then "
            "propagated to all companies through their cluster exposures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category_uris": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DMOZ/News category URIs. Omit to use defaults from config.",
                },
                "from_date": {
                    "type": "string",
                    "description": "Start date inclusive, YYYY-MM-DD",
                },
                "to_date": {
                    "type": "string",
                    "description": "End date inclusive, YYYY-MM-DD",
                },
            },
            "required": ["from_date", "to_date"],
        },
    },
    {
        "name": "store_scored_articles",
        "description": (
            "Persist scored company-specific articles to daily JSON files. "
            "Idempotent on article id — re-scoring overwrites. Pass the full "
            "array of scored article dicts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Uppercase stock ticker",
                },
                "articles": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Array of scored article dicts matching the schema",
                },
            },
            "required": ["ticker", "articles"],
        },
    },
    {
        "name": "store_macro_events",
        "description": (
            "Persist macro event scorings to daily JSON files. Idempotent on "
            "event id. Pass the full array of scored macro event dicts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Array of scored macro event dicts matching the schema",
                },
            },
            "required": ["events"],
        },
    },
    {
        "name": "compute_index",
        "description": (
            "Compute the daily sentiment index for a ticker. Reads stored "
            "company articles and macro events within the lookback window, "
            "applies exponential time-decay weighting, and returns the "
            "decomposed index (company + macro components)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Uppercase stock ticker",
                },
                "as_of_date": {
                    "type": "string",
                    "description": "Date to compute index for, YYYY-MM-DD",
                },
                "lookback_days": {
                    "type": "integer",
                    "description": "Lookback window in days (default 14)",
                },
                "decay_lambda": {
                    "type": "number",
                    "description": "Decay rate (default 0.231)",
                },
            },
            "required": ["ticker", "as_of_date"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool dispatch (kept for run_agent backward compat)
# ---------------------------------------------------------------------------

_STRIP_KEYS = {"categories", "concepts"}


def _strip_article_metadata(articles: list[dict]) -> list[dict]:
    """Remove bulky metadata the agent doesn't need for scoring."""
    return [
        {k: v for k, v in art.items() if k not in _STRIP_KEYS}
        for art in articles
    ]


def _execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return the JSON-serialised result."""
    if name == "get_company_profile":
        result = get_company_profile(args["ticker"])
    elif name == "fetch_company_news":
        articles = fetch_company_news(
            args["concept_uri"], args["from_date"], args["to_date"],
        )
        result = _strip_article_metadata(articles)
    elif name == "fetch_macro_news":
        articles = fetch_macro_news(
            category_uris=args.get("category_uris"),
            from_date=args["from_date"],
            to_date=args["to_date"],
        )
        result = _strip_article_metadata(articles)
    elif name == "store_scored_articles":
        count = store_scored_articles(args["ticker"], args["articles"])
        result = {"stored": count}
    elif name == "store_macro_events":
        count = store_macro_events(args["events"])
        result = {"stored": count}
    elif name == "compute_index":
        result = compute_index(
            args["ticker"],
            args["as_of_date"],
            lookback_days=args.get("lookback_days", 14),
            decay_lambda=args.get("decay_lambda", 0.231),
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Agent loop (kept for backward compat — no longer used by pipelines)
# ---------------------------------------------------------------------------

def run_agent(task: str, *, model: str = MODEL, max_turns: int = MAX_TURNS) -> str:
    """Run the agentic loop for a given task description.

    .. deprecated::
        Kept for backward compatibility.  The pipeline functions now use
        single-call scoring via :func:`score_company_articles` and
        :func:`score_macro_events`.

    Args:
        task: The user message describing the pipeline to run.
        model: Anthropic model ID.
        max_turns: Safety limit on conversation turns.

    Returns:
        The agent's final text response.
    """
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": task}]

    for turn in range(max_turns):
        logger.info("Agent turn %d", turn + 1)

        response = client.messages.create(
            model=model,
            max_tokens=16384,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Collect text and tool_use blocks
        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # If the model stopped naturally (no tool calls), we're done
        if response.stop_reason == "end_turn":
            # Extract final text
            text_parts = [
                block.text for block in assistant_content
                if block.type == "text"
            ]
            return "\n".join(text_parts)

        # Process tool calls
        tool_results = []
        for block in assistant_content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, json.dumps(block.input)[:200])
                result_str = _execute_tool(block.name, block.input)
                logger.info("Tool result: %s...", result_str[:300])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

        if not tool_results:
            break

        messages.append({"role": "user", "content": tool_results})

    return "(Agent reached max turns without completing)"


# ---------------------------------------------------------------------------
# Single-call scoring prompts
# ---------------------------------------------------------------------------

_COMPANY_SCORING_PROMPT = """\
You are a financial news sentiment scorer.  You receive a company profile and
a batch of news articles.  Return ONLY a JSON array of scored articles — no
commentary, no markdown fences, just the raw JSON array.

FILTERING RULES:
- Drop articles that are clearly tangential (company mentioned but not the subject).
- Use eventUri to deduplicate — if multiple articles share the same eventUri,
  keep only the highest-quality source (prefer Reuters, WSJ, Bloomberg, FT).

For EACH article kept, produce a dict with these exact keys:
- id: the article's "uri" field
- ticker: "{ticker}"
- headline: the article's "title"
- source: the article's source.uri (e.g. "reuters.com")
- url: the article's "url"
- published_at: the article's "dateTimePub"
- scored_at: "{scored_at}"
- event_uri: the article's "eventUri" (or null)
- article_tags: [2-5 free-form tags describing what this article covers]
- sentiment: [-1, +1] directional impact on THIS COMPANY, not article tone
- confidence: [0, 1] certainty of your sentiment call
- impact: [0, 1] materiality to fundamentals/stock price
- tag_similarity: {{
    "level_1_score": [0, 1] overlap with L1 Trends/Themes,
    "level_2_score": [0, 1] overlap with L2 cluster domains,
    "combined": level_1_score * 0.6 + level_2_score * 0.4
  }}
- final_score: sentiment * confidence * impact * combined_similarity

Sentiment guidance:
- "Competitor bankruptcy" = positive for this company
- "Analyst upgrades price target" = positive
- "NHTSA opens investigation" = negative
- "Routine quarterly update, in-line" = near zero

Impact scale:
- 0.8-1.0: CEO change, major M&A, earnings miss/beat, regulatory ruling
- 0.5-0.7: product launch, guidance change, significant partnership
- 0.2-0.4: analyst note, routine coverage, minor update
- < 0.2: tangential mention

Confidence scale:
- < 0.5: ambiguous, tangential, paywalled stub
- > 0.8: clear directional event directly about the company
"""

_MACRO_SCORING_PROMPT = """\
You are a macro news sentiment scorer.  You receive a batch of news articles
about macroeconomic, political, and policy events.  Return ONLY a JSON array
of scored events — no commentary, no markdown fences, just the raw JSON array.

FILTERING RULES:
- Use eventUri to deduplicate — if multiple articles share the same eventUri,
  keep only the highest-quality source (prefer Reuters, WSJ, Bloomberg, FT).

For EACH event kept, produce a dict with these exact keys:
- id: the article's "uri" field
- event_uri: the article's "eventUri" (or null)
- event_type: one of monetary_policy | fiscal_policy | trade_policy | geopolitical | regulatory | economic_data | political | other
- headline: the article's "title"
- source: the article's source.uri
- url: the article's "url"
- published_at: the article's "dateTimePub"
- scored_at: "{scored_at}"
- sentiment_direction: [-1, +1] overall market direction
- confidence: [0, 1]
- impact: [0, 1]
- cluster_impacts: directional impact [-1, +1] for each of these 8 clusters:
    "Mobility & Transport", "AI & Compute", "Energy & Grid",
    "Supply Chain & Trade", "Consumer Demand", "Capital Markets & Rates",
    "Regulatory & Policy", "Healthcare & Biotech"

Think about TRANSMISSION MECHANISMS — the same event affects different sectors differently:
- Rate hike: Capital Markets & Rates positive (banks), Consumer Demand negative
- Tariffs on China: Supply Chain & Trade negative, domestic Manufacturing positive

Set cluster_impacts to 0.0 for clusters not meaningfully affected.
"""


# ---------------------------------------------------------------------------
# Single-call scoring functions
# ---------------------------------------------------------------------------

def score_company_articles(
    ticker: str,
    profile: dict,
    articles: list[dict],
    *,
    model: str = MODEL,
) -> list[dict]:
    """Score company articles in a single Claude API call.

    Args:
        ticker: Uppercase stock ticker.
        profile: Company profile dict from :func:`get_company_profile`.
        articles: Raw articles from :func:`fetch_company_news` (already stripped).
        model: Anthropic model ID.

    Returns:
        List of scored article dicts ready for :func:`store_scored_articles`.
    """
    if not articles:
        return []

    scored_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    system = _COMPANY_SCORING_PROMPT.format(ticker=ticker, scored_at=scored_at)

    user_msg = (
        f"COMPANY PROFILE:\n{json.dumps(profile, indent=2)}\n\n"
        f"ARTICLES TO SCORE ({len(articles)} articles):\n"
        f"{json.dumps(articles, indent=2)}"
    )

    client = anthropic.Anthropic()
    logger.info("Scoring %d articles for %s (single call)", len(articles), ticker)

    response = client.messages.create(
        model=model,
        max_tokens=16384,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text
    return _parse_json_array(text)


def score_macro_events(
    articles: list[dict],
    *,
    model: str = MODEL,
) -> list[dict]:
    """Score macro news articles in a single Claude API call.

    Args:
        articles: Raw articles from :func:`fetch_macro_news` (already stripped).
        model: Anthropic model ID.

    Returns:
        List of scored macro event dicts ready for :func:`store_macro_events`.
    """
    if not articles:
        return []

    scored_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    system = _MACRO_SCORING_PROMPT.format(scored_at=scored_at)

    user_msg = (
        f"MACRO ARTICLES TO SCORE ({len(articles)} articles):\n"
        f"{json.dumps(articles, indent=2)}"
    )

    client = anthropic.Anthropic()
    logger.info("Scoring %d macro articles (single call)", len(articles))

    response = client.messages.create(
        model=model,
        max_tokens=16384,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text
    return _parse_json_array(text)


def _parse_json_array(text: str) -> list[dict]:
    """Extract a JSON array from model output, tolerating markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].rstrip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Pipeline wrappers (single-call approach)
# ---------------------------------------------------------------------------

def run_company_pipeline(
    ticker: str, from_date: str, to_date: str, *, model: str = MODEL,
) -> str:
    """Run Workflow A: company-specific news pipeline for a single ticker.

    Orchestration is done in Python.  Only the scoring step calls Claude,
    via a single API call (no multi-turn loop).
    """
    # Step 1: Load profile
    logger.info("[%s] Loading company profile", ticker)
    profile = get_company_profile(ticker)
    if profile is None:
        return f"No profile found for {ticker}. Skipping."

    concept_uri = profile.get("concept_uri")
    if not concept_uri:
        return f"Profile for {ticker} has no concept_uri. Skipping."

    # Step 2: Fetch news
    logger.info("[%s] Fetching company news %s to %s", ticker, from_date, to_date)
    raw_articles = fetch_company_news(concept_uri, from_date, to_date)
    articles = _strip_article_metadata(raw_articles)
    logger.info("[%s] Fetched %d articles", ticker, len(articles))

    if not articles:
        return f"No articles found for {ticker} in {from_date} to {to_date}."

    # Step 3: Score (single Claude API call)
    scored = score_company_articles(ticker, profile, articles, model=model)
    logger.info("[%s] Scored %d articles", ticker, len(scored))

    # Step 4: Store
    stored_count = store_scored_articles(ticker, scored)
    logger.info("[%s] Stored %d articles", ticker, stored_count)

    # Step 5: Compute index
    idx = compute_index(ticker, to_date)
    logger.info("[%s] Index: %+.4f (company: %+.4f, macro: %+.4f)",
                ticker, idx["index_value"],
                idx["company_component"], idx["macro_component"])

    # Step 6: Summary
    summary = (
        f"{ticker} sentiment index for {to_date}: {idx['index_value']:+.4f}\n"
        f"  Company component: {idx['company_component']:+.4f} "
        f"({idx['article_count']} articles)\n"
        f"  Macro component: {idx['macro_component']:+.4f} "
        f"({idx['macro_event_count']} events)"
    )
    return summary


def run_macro_pipeline(
    from_date: str, to_date: str, *, model: str = MODEL,
) -> str:
    """Run Workflow B: macro/political news pipeline (runs once per daily cycle).

    Orchestration is done in Python.  Only the scoring step calls Claude,
    via a single API call (no multi-turn loop).
    """
    # Step 1: Fetch macro news
    logger.info("Fetching macro news %s to %s", from_date, to_date)
    raw_articles = fetch_macro_news(from_date=from_date, to_date=to_date)
    articles = _strip_article_metadata(raw_articles)
    logger.info("Fetched %d macro articles", len(articles))

    if not articles:
        return f"No macro articles found for {from_date} to {to_date}."

    # Step 2: Score (single Claude API call — dedup + scoring in one pass)
    scored = score_macro_events(articles, model=model)
    logger.info("Scored %d macro events", len(scored))

    # Step 3: Store
    stored_count = store_macro_events(scored)
    logger.info("Stored %d macro events", stored_count)

    # Step 4: Summary
    return f"Macro pipeline: scored and stored {stored_count} events from {len(articles)} articles."
