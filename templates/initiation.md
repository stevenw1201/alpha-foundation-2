# {COMPANY_NAME} ({TICKER}) — Initiation of Coverage

**Date:** {DATE}
**Analyst:** Equity Research Agent

---

## Executive Summary

- {THESIS}
- {PRIMARY_CATALYST}
- {KEY_FINANCIAL_SIGNAL}
- {TECHNICAL_SETUP}

---

## Business Model & Value Chain

{BUSINESS_MODEL_NARRATIVE — operating model, revenue generation, product/service taxonomy, value chain position}

```diagram
{
    "title": "{COMPANY_NAME} — Value Chain",
    "direction": "TB",
    "nodes": [
        {"id": "A", "label": "Parent Company", "group": "core"},
        {"id": "B", "label": "Segment 1", "group": "segment"},
        {"id": "C", "label": "Product/Service", "group": "product"},
        {"id": "D", "label": "Revenue Driver", "group": "metric"}
    ],
    "edges": [
        {"from": "A", "to": "B"},
        {"from": "B", "to": "C"},
        {"from": "C", "to": "D"}
    ]
}
```

*Rendered to PNG via tools/diagram.py (Graphviz). Nodes auto-colored by group: core (dark blue), segment (blue), product (teal), stage (amber), outcome (diamond), metric (green).*

---

## Financial Health & Margins

{FINANCIAL_NARRATIVE}

### Historical Financials

| Metric | {Y1} | {Y2} | {Y3} | {Y4} | {Y5} |
|--------|-------|-------|-------|-------|-------|
| Revenue ($M) | | | | | |
| YoY Growth | | | | | |
| Gross Profit ($M) | | | | | |
| Gross Margin | | | | | |
| EBITDA ($M) | | | | | |
| EBITDA Margin | | | | | |
| Operating Income ($M) | | | | | |
| Operating Margin | | | | | |
| Net Income ($M) | | | | | |
| Net Margin | | | | | |

### Segment Breakdown

{SEGMENT_TABLE — by geography and/or product line where 10-K disclosures allow}

### Valuation Multiples

| Metric | Current | 5Y Avg | Peer Median |
|--------|---------|--------|-------------|
| EV/Revenue | | | |
| EV/EBITDA | | | |
| P/E (TTM) | | | |
| P/E (FWD) | | | |
| PEG | | | |

{CHART_REFERENCES — reference pre-generated PNGs from output/{TICKER}/charts/}

---

## Industry & Competitive Moat

### Macro Context

{MACRO_NARRATIVE — use FRED data to assess tailwind/headwind/neutral, one paragraph with reasoning}

### Peer Comparison

| Company | Revenue ($B) | Rev Growth | Gross Margin | EBITDA Margin | EV/EBITDA |
|---------|-------------|------------|--------------|---------------|-----------|
| **{COMPANY}** | | | | | |
| {PEER_1} | | | | | |
| {PEER_2} | | | | | |
| {PEER_3} | | | | | |

### Porter's Five Forces

| Force | Rating | Justification |
|-------|--------|---------------|
| Threat of New Entrants | | |
| Supplier Power | | |
| Buyer Power | | |
| Threat of Substitutes | | |
| Competitive Rivalry | | |

### Moat Assessment

**Type:** {MOAT_TYPES — network effects, switching costs, cost advantage, intangible assets, efficient scale}
**Durability:** {NONE / NARROW / WIDE}

{MOAT_EVIDENCE — specific evidence, not generic claims}

### Market Share

{MARKET_SHARE — overall and by segment/region, note data quality and source}

---

## Technical Setup & Timing

{TECHNICAL_NARRATIVE — "The current technical picture suggests..."}

### Indicator Summary

| Indicator | Value | Signal |
|-----------|-------|--------|
| 50-day SMA | | |
| 100-day SMA | | |
| 20-day EMA | | |
| 50-day EMA | | |
| RSI (14) | | |
| MACD | | |
| MACD Signal | | |
| Bollinger Position | | |
| OBV Trend | | |

**Support:** {SUPPORT_LEVELS}
**Resistance:** {RESISTANCE_LEVELS}

---

## Idiosyncratic Risks

| # | Risk | Type | Severity |
|---|------|------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

---

## Sources

1. {SOURCE_1}
2. {SOURCE_2}
3. {SOURCE_3}

---

## Tags

```yaml
# Level 1 — Specific Tags
Sectors:                # 1–2 tags, GICS sector level
  - name: ""
    score:

Industries:             # 1–3 tags, GICS industry/sub-industry level
  - name: ""
    score:

Trends:                 # 0–4 tags, broad secular/cyclical forces (10+ companies must share exposure)
  - name: ""
    score:

Themes:                 # 0–4 tags, investable baskets (not company-specific descriptors)
  - name: ""
    score:

# Level 2 — Theme Clusters (group Level 1 Trends/Themes into 3–6 broad domains)
Clusters:
  - name: ""            # Broad domain label (2–4 words), e.g. "AI & Compute", "Energy & Grid"
    relevance:          # Weighted avg of member tag scores
    member_tags:        # Which Level 1 Trends/Themes roll up here (min 2)
      - ""
      - ""

# Scoring: 70–100 = core driver | 40–69 = meaningful secondary | <40 = omit
# Breadth test: would filtering by this tag surface 10+ public companies?
# Cluster test: would a news desk organize a beat around this domain?
```
