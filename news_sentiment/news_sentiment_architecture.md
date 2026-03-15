# News Sentiment Agent — Architecture & Implementation Plan

*Version 2.0 | March 14, 2026*

---

## Mission

Produce a daily, per-ticker sentiment index by ingesting news, scoring it against the research agent's company profiles, and aggregating with time-decay weighting. Macro and political news is processed through a separate transmission layer that propagates directional impact through theme cluster exposures.

---

## System Overview

Two news pipelines feed into a unified daily index per company:

1. **Company-specific pipeline** — Entity-disambiguated news scored directly against the company profile
2. **Macro/political pipeline** — Category-filtered news scored once, then propagated to all companies through their cluster exposures

The research agent's initiation report (`.md` file with YAML tag block) is the upstream data contract. The sentiment agent consumes it; it never writes to it.

---

## Upstream Data Contract

### Research Agent Output

The research agent produces a full initiation report per ticker as a Markdown file:

```
output/{TICKER}_initiation_{YYYY-MM-DD}.md
```

The sentiment agent parses **only the YAML tag block** at the bottom of this file. Example structure from TSLA:

```yaml
# Level 1
Tags:
  Sectors:
    - { name: "Consumer Discretionary", score: 85 }
    - { name: "Industrials", score: 55 }
  Industries:
    - { name: "Automobile Manufacturers", score: 90 }
    - { name: "Electrical Equipment (Energy Storage)", score: 75 }
    - { name: "Application Software (FSD/AI)", score: 60 }
  Trends:
    - { name: "EV Adoption & Vehicle Electrification", score: 95 }
    - { name: "Autonomous Mobility", score: 88 }
    - { name: "AI Infrastructure Buildout", score: 72 }
    - { name: "Energy Transition & Grid Modernization", score: 85 }
  Themes:
    - { name: "Vertically Integrated EV Platforms", score: 90 }
    - { name: "Grid-Scale Battery Storage", score: 82 }
    - { name: "Robotics & Industrial Automation", score: 65 }
    - { name: "US-China Trade & Supply Chain Rebalancing", score: 70 }

# Level 2
Clusters:
  - name: "Mobility & Transport"
    relevance: 92
    member_tags:
      - "EV Adoption & Vehicle Electrification"
      - "Autonomous Mobility"
      - "Vertically Integrated EV Platforms"
  - name: "AI & Compute"
    relevance: 75
    member_tags:
      - "AI Infrastructure Buildout"
      - "Autonomous Mobility"
      - "Robotics & Industrial Automation"
  - name: "Energy & Grid"
    relevance: 84
    member_tags:
      - "Energy Transition & Grid Modernization"
      - "Grid-Scale Battery Storage"
  - name: "Supply Chain & Trade"
    relevance: 70
    member_tags:
      - "US-China Trade & Supply Chain Rebalancing"
      - "EV Adoption & Vehicle Electrification"
  - name: "Consumer Demand"
    relevance: 65
    member_tags:
      - "Vertically Integrated EV Platforms"
      - "EV Adoption & Vehicle Electrification"
  - name: "Regulatory & Policy"
    relevance: 68
    member_tags:
      - "Autonomous Mobility"
      - "Energy Transition & Grid Modernization"
      - "US-China Trade & Supply Chain Rebalancing"
```

The `get_company_profile` tool parses this YAML block from the .md file and returns it as structured JSON. The rest of the initiation report (financials, valuation, technicals) is not consumed by the sentiment agent.

### NewsAPI.ai Concept URI Mapping

Each ticker needs a mapped NewsAPI.ai concept URI for entity-disambiguated search. This is stored in a separate lookup file:

```json
// data/concept_map.json
{
  "TSLA": "http://en.wikipedia.org/wiki/Tesla,_Inc.",
  "GOOGL": "http://en.wikipedia.org/wiki/Alphabet_Inc.",
  "NVDA": "http://en.wikipedia.org/wiki/Nvidia",
  "JPM": "http://en.wikipedia.org/wiki/JPMorgan_Chase"
}
```

On first use for a new ticker, the agent can call `er.getConceptUri()` to resolve the mapping and persist it.

---

## Tool Inventory

### Tool 1: `fetch_company_news(concept_uri, from_date, to_date)`

**Type:** Deterministic (API plumbing)

**What it does:** Calls NewsAPI.ai article search filtered by concept URI (entity-disambiguated). Returns deduplicated articles with API-computed metadata.

**API parameters used:**
- `conceptUri` — entity-resolved company search (no keyword ambiguity)
- `categoryUri` — optional, filter to `news/Business` to stay in financial domain
- `isDuplicate: false` — API-level dedup
- `lang: "eng"` — English articles only (configurable)
- `includeArticleConcepts: true` — returns all entities mentioned
- `includeArticleCategories: true` — returns DMOZ category assignments
- `articlesSortBy: "date"` — most recent first

**Returns per article:**
```json
{
  "uri": "article_id",
  "title": "...",
  "body": "...",
  "url": "...",
  "dateTimePub": "2026-03-13T10:00:00Z",
  "source": { "uri": "reuters.com", "title": "Reuters" },
  "sentiment": 0.24,
  "eventUri": "eng-12345",
  "categories": [
    { "uri": "dmoz/Business/Investing", "wgt": 85 }
  ],
  "concepts": [
    { "uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.", "type": "org" }
  ]
}
```

**What the API handles (so the agent doesn't have to):**
- Entity disambiguation (no "Tesla the person" noise)
- Deduplication via `isDuplicate` flag
- Event clustering via `eventUri` (50 articles about the same Fed decision share one eventUri)
- Basic category classification via DMOZ taxonomy
- Pre-computed sentiment score (available but NOT used — agent does its own)

---

### Tool 2: `fetch_macro_news(category_uris[], from_date, to_date)`

**Type:** Deterministic (API plumbing)

**What it does:** Calls NewsAPI.ai filtered by macro/political category URIs. Returns deduplicated articles. The agent processes these through the macro scoring layer, not the company-specific pipeline.

**Default macro category URIs:**
```python
MACRO_CATEGORIES = [
    "dmoz/Business/Financial_Services/Banking",      # Monetary policy, central banks
    "news/Business",                                   # Broad business/economic
    "dmoz/Society/Government",                         # Political, regulatory
    "dmoz/Business/International_Business_and_Trade",  # Trade policy, tariffs
    "dmoz/Science/Technology",                         # Tech regulation, AI policy
    "news/Economy",                                    # Economic indicators
]
```

**Returns:** Same article structure as `fetch_company_news`. The agent uses categories and concepts to determine what type of macro event this is.

---

### Tool 3: `get_company_profile(ticker)`

**Type:** Deterministic (file parser)

**What it does:** Reads the research agent's initiation report `.md` file, extracts the YAML tag block, and returns structured JSON.

**Source file:** `data/profiles/{TICKER}_initiation_{latest_date}.md`

**Parsing logic:**
1. Find the ```` ```yaml ```` block within the `## Tags` section
2. Parse YAML into structured object
3. Also reads `data/concept_map.json` for the ticker's NewsAPI.ai concept URI

**Returns:**
```json
{
  "ticker": "TSLA",
  "concept_uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.",
  "level_1": {
    "sectors": [{ "name": "Consumer Discretionary", "score": 85 }, ...],
    "industries": [{ "name": "Automobile Manufacturers", "score": 90 }, ...],
    "trends": [{ "name": "EV Adoption & Vehicle Electrification", "score": 95 }, ...],
    "themes": [{ "name": "Vertically Integrated EV Platforms", "score": 90 }, ...]
  },
  "level_2_clusters": [
    {
      "name": "Mobility & Transport",
      "relevance": 92,
      "member_tags": ["EV Adoption & Vehicle Electrification", "Autonomous Mobility", "Vertically Integrated EV Platforms"]
    },
    ...
  ]
}
```

**If no profile exists for the ticker:** Returns `null`. Agent halts and logs — does not attempt to generate a profile.

---

### Tool 4: `store_scored_articles(ticker, articles[])`

**Type:** Deterministic (storage)

**What it does:** Persists the agent's scored company-specific articles. Appends to daily JSON file. Idempotent on article URI — re-scoring overwrites.

**Schema per scored article:**
```json
{
  "id": "article_uri",
  "ticker": "TSLA",
  "headline": "...",
  "source": "reuters.com",
  "url": "...",
  "published_at": "2026-03-13T10:00:00Z",
  "scored_at": "2026-03-13T14:00:00Z",
  "event_uri": "eng-12345",
  "article_tags": ["autonomous driving regulation", "robotaxi approval"],
  "sentiment": -0.35,
  "confidence": 0.80,
  "impact": 0.70,
  "tag_similarity": {
    "level_1_score": 0.85,
    "level_2_score": 0.90,
    "combined": 0.87
  },
  "final_score": -0.171
}
```

**Storage path:** `data/articles/{TICKER}/{YYYY-MM-DD}.json`

---

### Tool 5: `store_macro_events(events[])`

**Type:** Deterministic (storage)

**What it does:** Persists the agent's macro event scorings. Each event is scored once with a cluster impact vector, not per-ticker.

**Schema per macro event:**
```json
{
  "id": "article_uri",
  "event_uri": "eng-67890",
  "event_type": "monetary_policy",
  "headline": "Fed holds rates steady, signals cuts unlikely before Q4",
  "source": "wsj.com",
  "url": "...",
  "published_at": "2026-03-13T14:00:00Z",
  "scored_at": "2026-03-13T15:00:00Z",
  "sentiment_direction": -0.30,
  "confidence": 0.85,
  "impact": 0.70,
  "cluster_impacts": {
    "Mobility & Transport": -0.15,
    "AI & Compute": -0.20,
    "Energy & Grid": -0.10,
    "Supply Chain & Trade": -0.15,
    "Consumer Demand": -0.40,
    "Capital Markets & Rates": +0.60,
    "Regulatory & Policy": 0.00,
    "Healthcare & Biotech": -0.05
  }
}
```

**Key design choice:** `cluster_impacts` uses a universal cluster vocabulary — not company-specific cluster names. The propagation step maps these to each company's actual clusters by name matching. Companies that don't have a matching cluster get zero contribution from that cluster.

**Storage path:** `data/macro/{YYYY-MM-DD}.json`

---

### Tool 6: `compute_index(ticker, as_of_date, lookback_days, decay_lambda)`

**Type:** Deterministic (math)

**What it does:** Reads all scored company-specific articles AND all macro events within the lookback window. Computes the decayed, aggregated daily sentiment index for the given ticker.

**Company-specific component:**
```
For each scored article i:
  days_elapsed = as_of_date - published_at_i
  decayed_weight = exp(-decay_lambda × days_elapsed / impact_i)
  contribution_i = final_score_i × decayed_weight

company_sentiment = Σ contribution_i
```

**Macro component:**
```
For each macro event j:
  days_elapsed = as_of_date - published_at_j
  decayed_weight = exp(-decay_lambda × days_elapsed / impact_j)

  For each cluster in event's cluster_impacts:
    if company has matching cluster:
      cluster_contribution = cluster_impact × (company_cluster_relevance / 100)

  macro_contribution_j = Σ cluster_contributions × confidence_j × decayed_weight

macro_sentiment = Σ macro_contribution_j
```

**Combined index:**
```
daily_index = company_sentiment + macro_sentiment
```

**Returns:**
```json
{
  "ticker": "TSLA",
  "as_of_date": "2026-03-13",
  "index_value": -0.15,
  "company_component": +0.07,
  "macro_component": -0.22,
  "article_count": 12,
  "macro_event_count": 3,
  "top_company_contributors": [
    { "headline": "...", "contribution": +0.12, "days_old": 1 }
  ],
  "top_macro_contributors": [
    { "headline": "Fed holds...", "contribution": -0.18, "days_old": 0 }
  ],
  "index_history": [
    { "date": "2026-03-12", "value": -0.08, "company": +0.10, "macro": -0.18 },
    { "date": "2026-03-11", "value": +0.05, "company": +0.15, "macro": -0.10 }
  ]
}
```

---

## Agent Workflows

### Workflow A: Company-Specific Pipeline (per ticker)

**Step 1 — Load context.**
Agent calls `get_company_profile(ticker)`. If null → halt, log missing profile. Otherwise, agent now has L1 specific tags, L2 clusters, and the concept URI.

**Step 2 — Fetch news.**
Agent calls `fetch_company_news(concept_uri, from_date, to_date)`. The concept URI gives entity-disambiguated results — no keyword noise. Date range: last 24h for daily runs, wider for backfills. Agent may make 1-2 additional calls with high-relevance theme keywords if the concept search returns thin results.

**Step 3 — Filter.**
Agent reviews returned articles. The API already handled deduplication (`isDuplicate: false`) and entity disambiguation. Agent drops articles that are clearly tangential despite mentioning the company (e.g., "Tesla owner wins lottery" — mentions Tesla but is not investment-relevant). Agent also uses `eventUri` to group articles about the same event and pick the highest-quality source per event.

**Step 4 — Score each article.**
For each surviving article, the agent reasons through four dimensions:

*4a. Article tags:* What topics does this article cover? Free-form, no taxonomy constraint. Agent produces 2-5 descriptive tags. These will NOT match the company's L1 tags exactly — that's by design.

*4b. Sentiment:* On [-1, +1], what is the directional impact of this news on THIS COMPANY? This is NOT the article's general tone. "Competitor files for bankruptcy" is negative tone but potentially positive sentiment for the company. The agent also assigns confidence [0, 1].

*4c. Impact:* On [0, 1], how material is this event to the company's fundamentals or stock price? CEO resignation = high. Analyst reiteration = low. Routine quarterly update = medium.

*4d. Tag similarity:* The agent looks at its article tags alongside the company's L1 tags and L2 clusters. It makes a reasoned judgment about semantic overlap — not string matching, but conceptual relevance. Produces:
- `level_1_score` [0, 1]: how well article tags map to specific L1 Trends/Themes
- `level_2_score` [0, 1]: how well they map to L2 cluster domains
- `combined`: weighted blend (L1 × 0.6 + L2 × 0.4 by default; L2 weight increases when the connection is conceptual rather than direct)

*4e. Final score:* `sentiment × confidence × impact × tag_similarity.combined`

**Step 5 — Store.**
Agent calls `store_scored_articles(ticker, articles)`.

**Step 6 — Compute index.**
Agent calls `compute_index(ticker, today, 14, 0.231)`.

**Step 7 — Interpret (optional).**
Agent can produce natural language summary: "TSLA sentiment index at -0.15, with company-specific news mildly positive (+0.07) from Megapack contract coverage, offset by macro headwinds (-0.22) driven by the Fed hold and tariff escalation."

---

### Workflow B: Macro/Political Pipeline (runs once per daily cycle)

**Step 1 — Fetch macro news.**
Agent calls `fetch_macro_news(MACRO_CATEGORIES, from_date, to_date)`. Returns all macro/political articles from the last 24h.

**Step 2 — Group by event.**
Agent uses `eventUri` to group articles covering the same macro event (e.g., 30 articles about the Fed decision are one event). Picks the highest-quality source per event for scoring.

**Step 3 — Score each macro event.**
For each unique event, the agent reasons through:

*3a. Event classification:* What type of macro event is this? (monetary_policy, fiscal_policy, trade_policy, geopolitical, regulatory, economic_data, political, other)

*3b. Sentiment direction:* On [-1, +1], what is the overall directional tone of this development for markets?

*3c. Confidence:* [0, 1]. Lower for ambiguous or developing stories.

*3d. Impact:* [0, 1]. Fed rate decision = high. Minor economic revision = low.

*3e. Cluster impacts:* The key step. For each standard cluster, the agent assigns a directional impact [-1, +1]. This is where the agent reasons about transmission mechanisms:
- "Fed holds rates" → Capital Markets & Rates: +0.6 (banks benefit), Consumer Demand: -0.4 (borrowing costs stay high), AI & Compute: -0.2 (growth discount rate stays elevated)
- "New tariffs on Chinese goods" → Supply Chain & Trade: -0.5, Consumer Demand: -0.3, Manufacturing & Trade: mixed (+0.2 for domestic, -0.4 for importers)

The cluster vocabulary is NOT company-specific — it's a universal set that all companies' L2 clusters map into. The agent should use cluster names that match the research agent's L2 naming conventions.

**Step 4 — Store.**
Agent calls `store_macro_events(events)`.

**Step 5 — Done.**
Macro events are consumed by `compute_index` during per-ticker index computation. No separate index is needed for macro — it's a component of each company's index.

---

### Workflow C: Full Daily Run

```
1. Run Workflow B (macro pipeline) — once
2. For each ticker in universe:
   a. Run Workflow A (company pipeline)
   b. compute_index pulls from both company + macro stores
3. Output daily index values for all tickers
```

---

## Configuration

```yaml
# config.yaml

# NewsAPI.ai
newsapi_key: "YOUR_KEY"
newsapi_base_url: "https://eventregistry.org/api/v1"
default_lang: "eng"
source_rank_percentile: [0, 80]  # Top 80% of sources by traffic

# Macro category URIs
macro_categories:
  - "dmoz/Business/Financial_Services/Banking"
  - "news/Business"
  - "dmoz/Society/Government"
  - "dmoz/Business/International_Business_and_Trade"
  - "dmoz/Science/Technology"
  - "news/Economy"

# Scoring
decay_lambda: 0.231            # half-life ~3 days at impact=1.0
lookback_days: 14              # articles older than this drop out
confidence_floor: 0.3          # below this, article stored but excluded from index
tag_similarity_weights:
  level_1: 0.6
  level_2: 0.4

# Date ranges
company_news_lookback_hours: 24   # daily run
macro_news_lookback_hours: 24     # daily run
backfill_days: 30                 # for initial setup

# Universe
tickers:
  - TSLA
  - GOOGL
  - NVDA
  - MSFT
  - META
```

---

## Storage Schema

```
news_sentiment/
├── agent.py                  # Agent loop + system prompt + Claude API calls
├── tools/
│   ├── news.py               # fetch_company_news + fetch_macro_news (NewsAPI.ai)
│   ├── profile.py            # get_company_profile (parses .md YAML block)
│   ├── storage.py            # store_scored_articles + store_macro_events
│   └── index.py              # compute_index (decay math + aggregation)
├── data/
│   ├── profiles/             # Research agent .md files (read-only)
│   │   ├── TSLA_initiation_2026-03-14.md
│   │   ├── GOOGL_initiation_2026-03-12.md
│   │   └── ...
│   ├── concept_map.json      # Ticker → NewsAPI.ai concept URI mapping
│   ├── articles/             # Company-specific scored articles
│   │   ├── TSLA/
│   │   │   ├── 2026-03-13.json
│   │   │   └── 2026-03-14.json
│   │   └── GOOGL/
│   │       └── ...
│   ├── macro/                # Macro event scorings
│   │   ├── 2026-03-13.json
│   │   └── 2026-03-14.json
│   └── index/                # Running index history
│       ├── TSLA_index.json
│       └── GOOGL_index.json
├── config.yaml               # All configuration
└── run.py                    # Entry point — runs daily cycle
```

---

## Default Parameters & Calibration

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `decay_lambda` | 0.231 | Half-life of ~3 days at impact=1.0. High-impact articles (impact≈1.0) persist ~6 days; low-impact (impact≈0.3) fade in ~1 day. |
| `lookback_days` | 14 | Hard cutoff — articles older than 2 weeks contribute negligibly after decay. |
| `confidence_floor` | 0.3 | Articles below this confidence are stored (for audit) but excluded from index computation. |
| `L1 weight` | 0.6 | Specific tag matching gets more weight when there's direct overlap. |
| `L2 weight` | 0.4 | Cluster matching dominates when the connection is conceptual. |

All parameters should be calibrated against forward returns data once sufficient history exists. Target validation: monotonic relationship between sentiment quintiles and forward 1/5/20-day returns.

---

## Key Design Decisions

1. **Agent owns sentiment, API owns classification.** NewsAPI.ai handles entity disambiguation, deduplication, event clustering, and category assignment. The agent handles sentiment (directional for the company, not article tone), impact, confidence, and tag similarity. Clean separation — API does what NLP pipelines do well, agent does what LLMs do well.

2. **Macro scored once, propagated many.** A Fed decision is processed once through the macro pipeline, producing a cluster impact vector. That vector then propagates to every company through their L2 cluster relevance scores — deterministic math, not repeated LLM calls. Cost scales with news volume, not universe size.

3. **Two-level tag matching reduces agent burden.** Article tags won't match company tags exactly. L2 clusters provide a broad safety net (most articles map to at least one cluster), while L1 specific tags capture precision when there's direct overlap. The agent reasons about both levels simultaneously.

4. **Research agent is upstream authority.** The sentiment agent never generates or modifies company profiles. If a profile is missing, it halts. This prevents drift and keeps the analytical foundation consistent across the system.

5. **Decomposable index.** The daily index splits into company-specific and macro components. This is the real analytical value — "is this stock's sentiment driven by its own news or the macro environment?" drives fundamentally different portfolio decisions.

6. **Event-level deduplication for macro.** 50 articles about the same Fed decision share one `eventUri`. The agent scores the event once from the best source, not 50 times. This is critical for preventing volume bias in the macro component.
