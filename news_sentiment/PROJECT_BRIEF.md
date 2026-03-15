# News Sentiment Agent — Claude Code Project Brief

## What This Is

You are building a news sentiment index system. It ingests financial news, scores it against company profiles produced by a separate research agent, and computes a daily per-ticker sentiment index with exponential time-decay weighting.

Two pipelines feed into one unified index:
1. **Company-specific** — entity-disambiguated news scored directly against the company's tag profile
2. **Macro/political** — category-filtered news scored once with a cluster impact vector, then propagated to all companies through their L2 cluster exposures

## Key Files In This Repo

- `news_sentiment_architecture.md` — Full architecture doc. Contains tool schemas, agent workflows, scoring methodology, decay math, storage schemas, config defaults, and worked examples. **Read this first.**
- `research_agent_CLAUDE.md` — The research agent's system prompt. Shows how the upstream tag data is generated (Phase 4: Tagging with Level 1 specific tags + Level 2 theme clusters).
- `sample_data/TSLA_initiation_2026-03-14.md` — A real output from the research agent. The YAML tag block at the bottom of this file is what `get_company_profile` parses. This is your test fixture.

## Tech Stack

- Python 3.11+
- NewsAPI.ai (Event Registry) — `pip install eventregistry`
- Anthropic SDK — for the agent loop
- JSON file storage (SQLite migration later)
- PyYAML for parsing tag blocks from .md files

## Project Structure

```
news_sentiment/
├── agent.py              # Agent loop + system prompt + Claude API calls
├── tools/
│   ├── news.py           # fetch_company_news + fetch_macro_news (NewsAPI.ai)
│   ├── profile.py        # get_company_profile (parses .md YAML block)
│   ├── storage.py        # store_scored_articles + store_macro_events
│   └── index.py          # compute_index (decay math + aggregation)
├── data/
│   ├── profiles/         # Research agent .md files (read-only)
│   ├── concept_map.json  # Ticker → NewsAPI.ai concept URI mapping
│   ├── articles/         # Company-specific scored articles (per ticker)
│   ├── macro/            # Macro event scorings
│   └── index/            # Running index history
├── config.yaml           # All configuration
├── run.py                # Entry point — runs daily cycle
└── tests/
    ├── test_profile.py   # Test YAML parsing from .md files
    ├── test_index.py     # Test decay math with known inputs
    └── test_news.py      # Test NewsAPI.ai integration
```

## Build Order

### Step 1: `tools/profile.py` (no external dependencies)
Parse the YAML tag block from a research agent .md file. This is the foundation — every other tool depends on having a company profile.

### Step 2: `tools/index.py` (no external dependencies)
Pure math. Exponential decay + aggregation. Test with hardcoded scored articles to verify the formula behaves correctly.

### Step 3: `tools/storage.py` (no external dependencies)
JSON file read/write for scored articles and macro events. Idempotent on article ID.

### Step 4: `tools/news.py` (requires NewsAPI.ai key)
NewsAPI.ai integration. Two functions: concept URI search for company news, category filter for macro news.

### Step 5: `agent.py` + `run.py` (requires Anthropic API key)
The agent loop. System prompt encodes the scoring methodology. Calls tools in sequence.

### Step 6: Tests + calibration
Validate with TSLA data. Backfill 30 days. Check index behavior.

## Critical Implementation Details

### Profile Parsing
The research agent's .md file has a YAML block inside triple backticks at the bottom under `## Tags`. The parser needs to:
1. Find the ```yaml block
2. Handle the `# Level 1` and `# Level 2` comments (strip them or handle as YAML comments)
3. Parse into the structured JSON format specified in the architecture doc
4. Also read `data/concept_map.json` for the ticker's NewsAPI.ai concept URI

### Decay Formula
```
decayed_weight = exp(-lambda * days_elapsed / impact)
```
- lambda = 0.231 (half-life ~3 days at impact=1.0)
- impact is in the denominator: higher impact = slower decay
- Hard cutoff at 14 days lookback

### Index Decomposition
The daily index has two components:
```
daily_index = company_sentiment + macro_sentiment

company_sentiment = Σ (final_score_i × exp(-λ × t_i / impact_i))

macro_sentiment = Σ over events (
  Σ over clusters (cluster_impact × company_cluster_relevance/100)
  × confidence × exp(-λ × t / impact)
)
```

### Scoring (Agent-Owned)
The agent produces these per article:
- **sentiment** [-1, +1]: directional impact on the company (NOT article tone)
- **confidence** [0, 1]: how certain the agent is
- **impact** [0, 1]: materiality to fundamentals/stock price
- **tag_similarity**: L1 specific × 0.6 + L2 cluster × 0.4
- **final_score**: sentiment × confidence × impact × tag_similarity

### NewsAPI.ai Key Features Used
- `conceptUri` — entity-disambiguated company search
- `categoryUri` — DMOZ category filtering for macro news
- `isDuplicate: false` — API-level dedup
- `eventUri` — event clustering (group articles about same event)
- `includeArticleConcepts/Categories: true` — enriched metadata
- Pre-computed sentiment available but NOT used (agent does its own)
