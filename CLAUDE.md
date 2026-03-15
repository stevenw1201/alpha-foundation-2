# CLAUDE.md — News Sentiment Index

## What This Is

A financial news sentiment index system. It ingests news via NewsAPI.ai (Event Registry), scores articles against company tag profiles using a Claude-powered agent, and computes daily sentiment indices with exponential time-decay weighting.

Two pipelines feed a unified per-ticker index:
- **Company pipeline** — entity-disambiguated news scored against the company's L1/L2 tag profile
- **Macro pipeline** — category-filtered news scored once with cluster impact vectors, propagated to all companies through their cluster exposures

## Project Structure

```
news_sentiment/
├── agent.py              # Agentic loop (Claude tool use), system prompt, tool dispatch
├── run.py                # CLI entry point — daily cycle orchestration
├── config.yaml           # API keys, scoring params, ticker universe
├── tools/
│   ├── profile.py        # Parse company profiles from research agent .md files
│   ├── news.py           # NewsAPI.ai REST integration (headline-only, no body)
│   ├── storage.py        # Idempotent JSON persistence (articles, macro, index)
│   ├── index.py          # Decay math & index computation
│   └── chart.py          # Matplotlib charts (per-ticker + universe summary)
├── data/
│   ├── concept_map.json  # Ticker → NewsAPI.ai concept URI mapping
│   ├── profiles/         # Research agent initiation .md files (read-only input)
│   ├── articles/         # Scored company articles: articles/{TICKER}/{YYYY-MM-DD}.json
│   ├── macro/            # Scored macro events: macro/{YYYY-MM-DD}.json
│   └── index/            # Running index history: index/{TICKER}_index.json
└── tests/
    ├── test_profile.py   # YAML parsing from .md
    ├── test_news.py      # Mocked API calls, normalisation
    ├── test_storage.py   # JSON I/O idempotence
    ├── test_index.py     # Decay math, macro averaging, index decomposition
    ├── test_agent.py     # Agent loop, tool dispatch
    └── test_chart.py     # Chart file output
```

## Commands

```bash
# Run tests
python -m pytest news_sentiment/tests/ -v

# Run a specific test file
python -m pytest news_sentiment/tests/test_index.py -v

# Run the daily pipeline
python -m news_sentiment.run
python -m news_sentiment.run --ticker TSLA --from 2026-03-10 --to 2026-03-13
python -m news_sentiment.run --skip-macro --skip-charts
```

## Key Design Decisions

- **Headlines only** — articles are fetched without body text to reduce token usage. The agent scores from headline, source, and metadata.
- **Macro averaging** — macro contributions are averaged (not summed), then scaled by `macro_weight` (default 0.5). This prevents heavy macro days (Fed + tariffs + jobs data) from swamping the company signal.
- **Source quality filter** — `source_rank_percentile: [0, 50]` restricts to top-50 sources by reputation.
- **Decay formula** — `exp(-lambda * days / impact)` where `lambda=0.231` gives ~3-day half-life at impact=1.0. Higher-impact articles decay slower.
- **Confidence floor** — articles below `confidence_floor` (0.3) are excluded from the index entirely.

## Index Formula

```
index_value = company_component + macro_component

company_component = sum(final_score_i × exp(-λ × t_i / impact_i))

macro_component = mean(cluster_contribution_i × confidence_i × decay_weight_i) × macro_weight
```

Where `cluster_contribution = sum(cluster_impact × company_cluster_relevance / 100)` across matching clusters.

## Scoring Schema

Company articles produce: `sentiment`, `confidence`, `impact`, `tag_similarity` (L1×0.6 + L2×0.4), `final_score` (product of all four).

Macro events produce: `event_type`, `sentiment_direction`, `confidence`, `impact`, `cluster_impacts` (per-cluster directional floats for 8 standard clusters).

## Config (config.yaml)

Key parameters:
- `newsapi_key` — Event Registry API key
- `source_rank_percentile` — source quality filter `[start, end]`
- `decay_lambda` — exponential decay rate (0.231)
- `lookback_days` — hard cutoff window (14)
- `confidence_floor` — minimum confidence to include (0.3)
- `macro_weight` — scaling factor for averaged macro signal (0.5)
- `tickers` — universe of tracked companies

## Agent (agent.py)

Uses `claude-sonnet-4-20250514` with tool use. Max 25 turns. Tools:
- `get_company_profile(ticker)` → profile dict or null
- `fetch_company_news(concept_uri, from_date, to_date)` → articles
- `fetch_macro_news(category_uris?, from_date, to_date)` → articles
- `store_scored_articles(ticker, articles)` → count
- `store_macro_events(events)` → count
- `compute_index(ticker, as_of_date, ...)` → index dict

## Dependencies

Python 3.11+. Packages: `anthropic`, `requests`, `pyyaml`, `matplotlib`, `numpy`.

## Data Flow

```
Research Agent .md → profile.py → tag profile
                                        ↓
NewsAPI.ai → news.py → agent.py (scores) → storage.py → index.py → chart.py
                                        ↑
                              config.yaml (params)
```
