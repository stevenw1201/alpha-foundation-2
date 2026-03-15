"""Sentiment agent loop — orchestrates news fetching, scoring, and index computation.

Uses the Anthropic SDK with tool use.  The agent receives tool definitions,
decides which to call, gets results back, reasons, calls the next tool, and
repeats until it produces a final text response.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

import anthropic

from news_sentiment.tools.news import fetch_company_news, fetch_macro_news
from news_sentiment.tools.profile import get_company_profile
from news_sentiment.tools.storage import store_scored_articles, store_macro_events
from news_sentiment.tools.index import compute_index

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TURNS = 25

# ---------------------------------------------------------------------------
# System prompt
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
# Tool definitions (Claude tool_use format)
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
# Tool dispatch
# ---------------------------------------------------------------------------

def _execute_tool(name: str, args: dict) -> str:
    """Execute a tool call and return the JSON-serialised result."""
    if name == "get_company_profile":
        result = get_company_profile(args["ticker"])
    elif name == "fetch_company_news":
        articles = fetch_company_news(
            args["concept_uri"], args["from_date"], args["to_date"],
        )
        result = articles
    elif name == "fetch_macro_news":
        articles = fetch_macro_news(
            category_uris=args.get("category_uris"),
            from_date=args["from_date"],
            to_date=args["to_date"],
        )
        result = articles
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
# Agent loop
# ---------------------------------------------------------------------------

def run_agent(task: str, *, model: str = MODEL, max_turns: int = MAX_TURNS) -> str:
    """Run the agentic loop for a given task description.

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
            # No tool calls and no end_turn — shouldn't happen, but break to be safe
            break

        messages.append({"role": "user", "content": tool_results})

    # If we exhausted turns, return whatever text we have
    return "(Agent reached max turns without completing)"


# ---------------------------------------------------------------------------
# Pipeline wrappers
# ---------------------------------------------------------------------------

def run_company_pipeline(
    ticker: str, from_date: str, to_date: str, *, model: str = MODEL,
) -> str:
    """Run Workflow A: company-specific news pipeline for a single ticker."""
    task = (
        f"Run the COMPANY-SPECIFIC pipeline for {ticker}.\n"
        f"Date range: {from_date} to {to_date}.\n\n"
        f"Steps:\n"
        f"1. Call get_company_profile for {ticker}\n"
        f"2. Use the concept_uri to call fetch_company_news\n"
        f"3. Filter and score all returned articles\n"
        f"4. Call store_scored_articles with {ticker} and your scored articles\n"
        f"5. Call compute_index for {ticker} with as_of_date={to_date}\n"
        f"6. Provide a brief summary of the index result\n"
    )
    return run_agent(task, model=model)


def run_macro_pipeline(
    from_date: str, to_date: str, *, model: str = MODEL,
) -> str:
    """Run Workflow B: macro/political news pipeline (runs once per daily cycle)."""
    task = (
        f"Run the MACRO/POLITICAL pipeline.\n"
        f"Date range: {from_date} to {to_date}.\n\n"
        f"Steps:\n"
        f"1. Call fetch_macro_news for the date range (use default categories)\n"
        f"2. Group articles by eventUri — pick the best source per event\n"
        f"3. Score each unique macro event with event_type, sentiment_direction,\n"
        f"   confidence, impact, and cluster_impacts\n"
        f"4. Call store_macro_events with your scored events\n"
        f"5. Report how many events were processed and stored\n"
    )
    return run_agent(task, model=model)
