# TODO — News Sentiment Index

## Pre-Production Blocklist

### Pipeline Gaps
- [ ] **Scored JSON validation** — no schema check on LLM output. If Haiku returns malformed scores (sentiment outside [-1,1], missing keys), it silently propagates. Add pydantic or manual validation after `_parse_json_array`.
- [ ] **API failure handling** — no retry/backoff for NewsAPI.ai rate limits or Anthropic outages. A single 429/500 kills the whole ticker's pipeline.
- [ ] **Backfill strategy** — the index needs 14 days of lookback history. First run produces a thin index. Need a one-time backfill pass using `--from` / `--to` over the prior 14–30 days.
- [ ] **Scheduling / cron** — nothing triggers the daily run. Need cron, Airflow, or a simple systemd timer.
- [ ] **Monitoring / alerting** — if the pipeline silently fails (no articles, bad scores, API down), nobody knows. Need health checks and alerts.

### Data / Config Gaps
- [ ] **concept_map.json** — only 5 tickers mapped. Need concept URIs for all 500 S&P tickers before scaling.
- [ ] **config.yaml API key** — hardcoded in the file. Move to environment variable or secrets manager.
- [ ] **Profiles** — only have research agent .md files for the 5 test tickers. Need profiles for the full universe.

### Quality Assurance
- [ ] **Haiku vs Sonnet scoring comparison** — need to run both models on the same article batch and diff the scores before committing to Haiku for production. Key concerns: tag_similarity accuracy, edge-case sentiment calls (e.g., "competitor bankruptcy = positive").
- [ ] **Macro category coverage** — current config has 6 DMOZ/news categories. May miss: energy policy, labor/employment, central bank communications outside "Banking", commodity shocks, climate/weather events.

---

## NewsAPI.ai Integration — Missing Parameters

### Currently Using
- `conceptUri` (company) / `categoryUri` (macro)
- `lang: "eng"`
- `dateStart` / `dateEnd`
- `isDuplicateFilter: "skipDuplicates"`
- `includeArticleConcepts: True`
- `includeArticleCategories: True`
- `articlesSortBy: "date"`
- `articlesCount: 100`
- `startSourceRankPercentile` / `endSourceRankPercentile`

### Should Add
- [ ] **`dataType: "news"`** — we're not filtering out press releases (`"pr"`) and blog posts (`"blog"`). PR newswire articles are corporate spin, not independent journalism. Will pollute sentiment scores with positive-biased fluff.
- [ ] **`includeArticleSentiment: True`** — Event Registry provides its own NLP sentiment score. Useful as a baseline/sanity check against our LLM scores — if they diverge wildly and consistently, something is wrong.
- [ ] **`includeArticleSocialScore: True`** — social share counts (Facebook, Twitter, LinkedIn) are a free proxy for article reach/impact. Could inform the `impact` score or serve as a secondary signal.
- [ ] **`includeArticleAuthors: True`** — author identity could help with source credibility weighting (e.g., known analysts vs generic wire copy).

### Should Consider
- [ ] **Pagination** — `articlesCount: 100` is a hard cap. On heavy news days (earnings season, Fed day, tariff announcements), a major ticker could easily have 100+ articles. We'd miss the tail. Need either pagination or a higher cap with cost awareness.
- [ ] **`minSentiment` / `maxSentiment`** — could pre-filter neutral articles at the API level to reduce token usage. Risk: Event Registry's sentiment != our sentiment (they score article tone, we score company impact).
- [ ] **`locationUri`** — for macro news, filtering by US/EU/China locations could improve relevance vs catching every global article.
- [ ] **`keywordOper` + `keyword`** — for macro pipeline, adding keyword filters (e.g., "Federal Reserve", "tariff", "GDP") alongside category URIs would improve precision.

### Not Needed
- `includeArticleBody` — deliberately excluded (headlines-only design for token efficiency)
- `includeArticleImage` — no use case
- `includeArticleVideos` — no use case
- `includeArticleLinks` — no use case

---

## Macro Category Gaps

Current categories:
```yaml
macro_categories:
  - "dmoz/Business/Financial_Services/Banking"
  - "news/Business"
  - "dmoz/Society/Government"
  - "dmoz/Business/International_Business_and_Trade"
  - "dmoz/Science/Technology"
  - "news/Economy"
```

Potentially missing:
- [ ] **Energy / commodities** — oil price shocks, OPEC decisions, natural gas. No energy-specific category.
- [ ] **Labor / employment** — jobs reports, strikes, wage data. Critical macro signal.
- [ ] **Central banking (non-US)** — ECB, BOJ, PBOC decisions affect US markets. "Banking" may not catch these.
- [ ] **Climate / weather** — extreme weather events, climate policy (IRA, EU carbon border). Increasingly material.
- [ ] **Defense / geopolitical** — military conflicts, sanctions. "Society/Government" is broad, may miss defense-specific news.
