# News Sentiment Index — Changelog & Development Notes

## Version History

### v0.6 — API Request Quality (2026-03-15)

**Changes:**
- Added `dataType: ["news"]` to both company and macro API calls — filters out PR newswire, blog posts, and press releases that systematically inflate positive sentiment
- Bumped default `max_articles` from 100 to 200 to reduce silent article drops on heavy news days (earnings, Fed announcements)
- Added `includeArticleSentiment: True` — Event Registry's own sentiment now returned for cross-validation against our Haiku scores
- Added `includeArticleSocialScore: True` — social reach/virality metric captured in normalised schema for future correlation analysis

**Why it matters:** PR newswire articles are corporate marketing disguised as news. Without the `dataType` filter, every ticker's sentiment was biased positive. The 100-article cap was also silently truncating results on busy days — TSLA on an earnings day easily exceeds 100 articles.

---

### v0.5 — TODO & Pre-Production Gap Audit (2026-03-15)

- Added `TODO.md` documenting all known pre-production blockers
- Catalogued NewsAPI.ai parameter gaps and improvement opportunities

---

### v0.4 — Scoring Model Optimisation (2026-03-14)

**Changes:**
- Switched company article scoring from Sonnet to **Haiku 4.5** (`claude-haiku-4-5-20251001`) for cost reduction
- Kept **Sonnet** (`claude-sonnet-4-20250514`) for macro event scoring where nuanced multi-cluster reasoning is critical
- Refactored agent from multi-turn agentic loop to **single-call scoring** — Python orchestrates, Claude only scores
- Strip categories and concepts from article payloads before sending to agent (token savings)

**Why it matters:** The old multi-turn loop burned tokens on tool-call overhead and duplicated output. Single-call scoring is ~3x cheaper per run. Haiku handles company headlines well; macro events need Sonnet's reasoning for cluster impact vectors.

---

### v0.3 — Signal Quality Fixes (2026-03-13)

**Changes:**
- Tightened source quality filter from top-80 to **top-50 percentile** — prefers Reuters, WSJ, Bloomberg, FT
- Fixed macro accumulation bias: **average** macro events instead of summing — prevents heavy macro days (Fed + tariffs + jobs data) from swamping company signal
- Switched to **headlines only** — dropped article body text entirely to reduce token usage

**Why it matters:** Summing macro events meant a day with 5 events contributed 5x more than a day with 1 event, regardless of individual event quality. Averaging with `macro_weight` scaling (0.5) keeps macro proportional to the company signal.

---

### v0.2 — Core Pipeline (2026-03-12)

- Added `agent.py` — agentic loop with Claude tool use and system prompt
- Added `run.py` — CLI entry point with `--ticker`, `--from`, `--to`, `--skip-macro`, `--skip-charts`
- Added `tools/chart.py` — per-ticker timeseries and universe summary charts
- Added `compute_index_range` for daily index over date windows

---

### v0.1 — Foundation (2026-03-11)

- Added `tools/profile.py` — parse company profiles from research agent `.md` files
- Added `tools/news.py` — NewsAPI.ai REST integration
- Added `tools/storage.py` — idempotent JSON persistence for articles and macro events
- Added `tools/index.py` — exponential decay index computation with macro propagation
- Added `data/concept_map.json` — ticker-to-concept URI mapping (5 tickers)
- Added `config.yaml` with scoring parameters

---

## Current Architecture

```
Research Agent .md → profile.py → tag profile
                                        ↓
NewsAPI.ai → news.py → agent.py (scores) → storage.py → index.py → chart.py
                                        ↑
                              config.yaml (params)
```

**Models:** Haiku 4.5 (company scoring), Sonnet (macro scoring)
**Universe:** TSLA, GOOGL, NVDA, MSFT, META
**Tests:** 112 passing

---

## Things to Avoid

### API & Data
- **Do NOT use `minSentiment`/`maxSentiment` pre-filtering** — Event Registry's sentiment != ours. Pre-filtering at the API level risks dropping articles our model would score differently.
- **Do NOT fetch article bodies** — deliberately excluded to reduce token cost. Headlines + source metadata are sufficient for scoring.
- **Do NOT sum macro events** — always average, then scale by `macro_weight`. Summing creates day-volume bias.
- **Do NOT use `locationUri` yet** — adds complexity with unclear payoff at current scale.

### Scoring
- **Do NOT trust Haiku for macro scoring** — cluster impact vectors require multi-step reasoning that Haiku struggles with. Keep Sonnet for macro.
- **Do NOT remove the confidence floor (0.3)** — low-confidence articles add noise without signal. The floor is load-bearing.
- **Do NOT change `decay_lambda` without re-validating** — 0.231 gives ~3-day half-life at impact=1.0. This was calibrated to news cycle dynamics.

### Infrastructure
- **Do NOT hardcode API keys in committed config** — `config.yaml` currently has the key inline. Must move to env var before production.
- **Do NOT skip deduplication** — `isDuplicateFilter: "skipDuplicates"` is essential. Without it, syndicated articles (AP/Reuters rewrites) create false signal amplification.

---

## Things to Note

### Known Limitations
1. **No LLM output validation** — if Haiku returns malformed scores (sentiment outside [-1,1], missing keys), they propagate silently into the index
2. **No API retry/backoff** — a single NewsAPI.ai 429 or Anthropic outage kills the entire ticker's pipeline
3. **Thin index on first run** — the decay formula needs 14 days of lookback history; first runs produce unreliable indices until backfill completes
4. **5-ticker universe** — only TSLA, GOOGL, NVDA, MSFT, META are mapped in `concept_map.json`

### Design Decisions Worth Remembering
- **Tag similarity = L1×0.6 + L2×0.4** — L1 (sectors, industries, trends, themes) weighted higher than L2 (cluster-level tags) because L1 captures broader relevance
- **`final_score` = sentiment × confidence × impact × tag_similarity** — multiplicative, not additive. A zero in any dimension zeros the whole score. This is intentional.
- **Macro propagation via cluster exposures** — macro events don't score per-company. They score once with cluster impact vectors, then propagate through each company's L2 cluster relevance weights.
- **`socialScore` is stored but not used in scoring** — captured for future correlation analysis. Do not add it to the scoring formula without validating it adds signal.

### Macro Category Coverage Gaps
Current categories cover banking, business, government, trade, technology, economy. Missing:
- Energy policy
- Labor/employment
- Central bank communications outside US (ECB, BOJ, PBOC)
- Commodities
- Climate/weather events

### Parameter Quick Reference
| Parameter | Value | Notes |
|---|---|---|
| `decay_lambda` | 0.231 | ~3-day half-life at impact=1.0 |
| `lookback_days` | 14 | Hard cutoff window |
| `confidence_floor` | 0.3 | Articles below excluded |
| `macro_weight` | 0.5 | Scaling for averaged macro signal |
| `source_rank_percentile` | [0, 50] | Top-50 sources only |
| `max_articles` | 200 | Per API call |
| `dataType` | ["news"] | Excludes PR/blog/press releases |
