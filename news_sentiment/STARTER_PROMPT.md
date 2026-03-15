# Claude Code Starter Prompt

Paste this as your first message in Claude Code after setting up the project directory.

---

## Prompt:

```
I'm building a news sentiment index system. Read these files first:
- PROJECT_BRIEF.md — project overview and build order
- news_sentiment_architecture.md — full architecture spec
- sample_data/TSLA_initiation_2026-03-14.md — real output from the research agent (test fixture)

We're starting with Step 1: `tools/profile.py`

Build the `get_company_profile(ticker)` function that:

1. Looks for the most recent initiation .md file in `data/profiles/` matching the pattern `{TICKER}_initiation_*.md`
2. Extracts the YAML tag block from inside the ```yaml fenced code block under the `## Tags` section
3. Handles the `# Level 1` and `# Level 2` YAML comments (they need to be stripped or the YAML won't parse cleanly — split the block at `# Level 2` and parse each half separately)
4. Reads `data/concept_map.json` for the ticker's NewsAPI.ai concept URI
5. Returns a structured dict matching this schema:

{
  "ticker": "TSLA",
  "concept_uri": "http://en.wikipedia.org/wiki/Tesla,_Inc.",
  "level_1": {
    "sectors": [{"name": "...", "score": N}, ...],
    "industries": [...],
    "trends": [...],
    "themes": [...]
  },
  "level_2_clusters": [
    {"name": "...", "relevance": N, "member_tags": ["...", "..."]}
  ]
}

Returns None if no profile exists for the ticker.

Also:
- Set up the project directory structure (news_sentiment/ with tools/, data/, data/profiles/, data/articles/, data/macro/, data/index/, tests/)
- Create config.yaml with the defaults from the architecture doc
- Copy the TSLA sample file into data/profiles/ for testing
- Write test_profile.py that validates the parser against the TSLA file — check that it correctly extracts all L1 tags with scores and all L2 clusters with member tags
- Use PyYAML for parsing

After profile.py works, we'll move to tools/index.py (decay math).
```
