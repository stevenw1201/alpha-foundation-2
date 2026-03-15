"""
FRED Macro Data Pipeline
Fetches economic indicators from the FRED API for macro context in equity research.

Usage:
    python tools/fred.py --query "rates inflation"
    python tools/fred.py --indicators FEDFUNDS,CPIAUCSL,T10Y2Y --period 5y
    python tools/fred.py --preset equity_macro
    python tools/fred.py --preset energy_sector

Requires FRED_API_KEY environment variable.
Get one free at: https://fred.stlouisfed.org/docs/api/api_key.html
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests --break-system-packages")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FRED_BASE = "https://api.stlouisfed.org/fred"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fred"
CACHE_TTL = 3600  # 1 hour cache

# ---------------------------------------------------------------------------
# Indicator Presets
# ---------------------------------------------------------------------------
PRESETS = {
    "equity_macro": {
        "description": "Core macro indicators for equity research",
        "indicators": {
            "FEDFUNDS": "Fed Funds Rate",
            "DFF": "Daily Fed Funds Effective Rate",
            "T10Y2Y": "10Y-2Y Treasury Spread",
            "DGS10": "10-Year Treasury Yield",
            "DGS2": "2-Year Treasury Yield",
            "CPIAUCSL": "CPI (All Urban, SA)",
            "CPILFESL": "Core CPI (ex Food & Energy)",
            "UNRATE": "Unemployment Rate",
            "PAYEMS": "Total Nonfarm Payrolls",
            "ISM-MAN_PMI": "ISM Manufacturing PMI",
            "RSAFS": "Retail Sales (ex Food Services)",
            "INDPRO": "Industrial Production Index",
            "UMCSENT": "U of Michigan Consumer Sentiment",
            "VIXCLS": "CBOE VIX",
            "BAMLH0A0HYM2": "ICE BofA US HY OAS",
        },
    },
    "energy_sector": {
        "description": "Energy sector macro context",
        "indicators": {
            "DCOILWTICO": "WTI Crude Oil",
            "DCOILBRENTEU": "Brent Crude Oil",
            "DHHNGSP": "Henry Hub Natural Gas",
            "GASREGW": "Regular Gasoline Price",
            "IPG2211A2N": "Electric Power Generation Index",
            "TOTDTIQ027S": "Total Credit to Non-Financial Sector",
        },
    },
    "housing": {
        "description": "Housing & real estate indicators",
        "indicators": {
            "MORTGAGE30US": "30-Year Fixed Mortgage Rate",
            "HOUST": "Housing Starts",
            "PERMIT": "Building Permits",
            "MSPUS": "Median Home Sale Price",
            "CSUSHPINSA": "Case-Shiller Home Price Index",
            "RRVRUSQ156N": "Rental Vacancy Rate",
        },
    },
    "tech_growth": {
        "description": "Indicators relevant to tech/growth equities",
        "indicators": {
            "FEDFUNDS": "Fed Funds Rate",
            "DGS10": "10-Year Treasury Yield",
            "T10YIE": "10-Year Breakeven Inflation",
            "BAMLH0A0HYM2": "ICE BofA US HY OAS",
            "NASDAQCOM": "NASDAQ Composite",
            "VIXCLS": "CBOE VIX",
            "BOGZ1FL073164003Q": "Corporate Profits After Tax",
            "CPIAUCSL": "CPI (All Urban, SA)",
        },
    },
}

# Full 71-indicator universe (abbreviated here, extend as needed)
INDICATOR_METADATA = {
    "FEDFUNDS": {"category": "Rates", "frequency": "monthly", "unit": "%"},
    "DFF": {"category": "Rates", "frequency": "daily", "unit": "%"},
    "DGS10": {"category": "Rates", "frequency": "daily", "unit": "%"},
    "DGS2": {"category": "Rates", "frequency": "daily", "unit": "%"},
    "T10Y2Y": {"category": "Rates", "frequency": "daily", "unit": "%"},
    "CPIAUCSL": {"category": "Inflation", "frequency": "monthly", "unit": "index"},
    "CPILFESL": {"category": "Inflation", "frequency": "monthly", "unit": "index"},
    "UNRATE": {"category": "Labor", "frequency": "monthly", "unit": "%"},
    "PAYEMS": {"category": "Labor", "frequency": "monthly", "unit": "thousands"},
    "VIXCLS": {"category": "Volatility", "frequency": "daily", "unit": "index"},
    "BAMLH0A0HYM2": {"category": "Credit", "frequency": "daily", "unit": "%"},
    "DCOILWTICO": {"category": "Energy", "frequency": "daily", "unit": "$/barrel"},
}


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_api_key() -> str:
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        print("WARNING: FRED_API_KEY not set. Set it with: export FRED_API_KEY='your_key'")
        print("Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        print("Falling back to cached data if available.\n")
    return key


def parse_period(period_str: str) -> datetime:
    """Parse period string like '5y', '2y', '6m', '90d' into a start date."""
    now = datetime.now()
    val = int(period_str[:-1])
    unit = period_str[-1].lower()
    if unit == "y":
        return now - timedelta(days=val * 365)
    elif unit == "m":
        return now - timedelta(days=val * 30)
    elif unit == "d":
        return now - timedelta(days=val)
    else:
        raise ValueError(f"Unknown period unit: {unit}. Use y/m/d.")


def fetch_series(series_id: str, api_key: str, start_date: str, end_date: str) -> dict:
    """Fetch a single FRED series with caching."""
    cache_key = f"{series_id}_{start_date}_{end_date}"
    cache_path = DATA_DIR / f"{cache_key}.json"

    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime < CACHE_TTL):
        return json.loads(cache_path.read_text())

    if not api_key:
        if cache_path.exists():
            print(f"  Using cached data for {series_id}")
            return json.loads(cache_path.read_text())
        return {"series_id": series_id, "error": "No API key and no cache available"}

    url = (
        f"{FRED_BASE}/series/observations?"
        f"series_id={series_id}&api_key={api_key}&file_type=json"
        f"&observation_start={start_date}&observation_end={end_date}"
        f"&sort_order=desc"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        observations = data.get("observations", [])

        result = {
            "series_id": series_id,
            "count": len(observations),
            "observations": observations[:24],  # Keep last 24 data points
            "latest": observations[0] if observations else None,
        }

        # Add metadata
        meta_url = (
            f"{FRED_BASE}/series?series_id={series_id}"
            f"&api_key={api_key}&file_type=json"
        )
        meta_resp = requests.get(meta_url, timeout=10)
        if meta_resp.status_code == 200:
            serieses = meta_resp.json().get("serieses", [])
            if serieses:
                result["title"] = serieses[0].get("title", "")
                result["units"] = serieses[0].get("units", "")
                result["frequency"] = serieses[0].get("frequency", "")

        cache_path.write_text(json.dumps(result, indent=2))
        time.sleep(0.2)  # Rate limit
        return result

    except Exception as e:
        print(f"  ERROR fetching {series_id}: {e}")
        if cache_path.exists():
            return json.loads(cache_path.read_text())
        return {"series_id": series_id, "error": str(e)}


def query_to_indicators(query: str) -> list[str]:
    """Map a natural language query to relevant indicator IDs."""
    query_lower = query.lower()
    keyword_map = {
        "rate": ["FEDFUNDS", "DFF", "DGS10", "DGS2"],
        "rates": ["FEDFUNDS", "DFF", "DGS10", "DGS2"],
        "inflation": ["CPIAUCSL", "CPILFESL", "T10YIE"],
        "cpi": ["CPIAUCSL", "CPILFESL"],
        "yield": ["DGS10", "DGS2", "T10Y2Y"],
        "spread": ["T10Y2Y", "BAMLH0A0HYM2"],
        "credit": ["BAMLH0A0HYM2"],
        "labor": ["UNRATE", "PAYEMS"],
        "employment": ["UNRATE", "PAYEMS"],
        "unemployment": ["UNRATE"],
        "jobs": ["PAYEMS", "UNRATE"],
        "oil": ["DCOILWTICO", "DCOILBRENTEU"],
        "energy": ["DCOILWTICO", "DHHNGSP"],
        "gas": ["DHHNGSP", "GASREGW"],
        "vix": ["VIXCLS"],
        "volatility": ["VIXCLS"],
        "housing": ["HOUST", "PERMIT", "MORTGAGE30US", "CSUSHPINSA"],
        "mortgage": ["MORTGAGE30US"],
        "consumer": ["UMCSENT", "RSAFS"],
        "sentiment": ["UMCSENT"],
        "retail": ["RSAFS"],
        "manufacturing": ["ISM-MAN_PMI", "INDPRO"],
        "pmi": ["ISM-MAN_PMI"],
    }

    indicators = set()
    for keyword, ids in keyword_map.items():
        if keyword in query_lower:
            indicators.update(ids)

    if not indicators:
        # Default to core macro set
        indicators = {"FEDFUNDS", "DGS10", "CPIAUCSL", "UNRATE", "VIXCLS"}
        print(f"  No keyword match for '{query}', using core macro defaults")

    return sorted(indicators)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FRED Macro Data Pipeline")
    parser.add_argument("--query", default=None, help="Natural language query for relevant indicators")
    parser.add_argument("--indicators", default=None, help="Comma-separated FRED series IDs")
    parser.add_argument("--preset", default=None, choices=list(PRESETS.keys()),
                        help="Use a predefined indicator set")
    parser.add_argument("--period", default="2y", help="Lookback period (e.g., 5y, 6m, 90d)")
    parser.add_argument("--json", action="store_true", help="Save full output as JSON")
    parser.add_argument("--list-presets", action="store_true", help="List available presets")

    args = parser.parse_args()
    ensure_data_dir()

    if args.list_presets:
        print("Available presets:")
        for name, info in PRESETS.items():
            print(f"  {name}: {info['description']}")
            for sid, label in info["indicators"].items():
                print(f"    - {sid}: {label}")
        return

    api_key = get_api_key()
    start_date = parse_period(args.period).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    # Determine which indicators to fetch
    indicator_ids = []
    labels = {}

    if args.preset:
        preset = PRESETS[args.preset]
        print(f"=== FRED Preset: {args.preset} — {preset['description']} ===\n")
        indicator_ids = list(preset["indicators"].keys())
        labels = preset["indicators"]
    elif args.indicators:
        indicator_ids = [s.strip() for s in args.indicators.split(",")]
        labels = {s: s for s in indicator_ids}
        print(f"=== FRED Custom: {', '.join(indicator_ids)} ===\n")
    elif args.query:
        indicator_ids = query_to_indicators(args.query)
        labels = {s: INDICATOR_METADATA.get(s, {}).get("category", s) for s in indicator_ids}
        print(f"=== FRED Query: '{args.query}' → {len(indicator_ids)} indicators ===\n")
    else:
        print("ERROR: Provide --query, --indicators, or --preset")
        parser.print_help()
        sys.exit(1)

    # Fetch all series
    results = {}
    for sid in indicator_ids:
        label = labels.get(sid, sid)
        print(f"Fetching {sid} ({label})...")
        data = fetch_series(sid, api_key, start_date, end_date)
        results[sid] = data

        if "error" not in data and data.get("latest"):
            latest = data["latest"]
            title = data.get("title", label)
            units = data.get("units", "")
            val = latest.get("value", "N/A")
            date = latest.get("date", "")
            print(f"  → {title}: {val} {units} (as of {date})")
        elif "error" in data:
            print(f"  → ERROR: {data['error']}")

    # Summary table
    print(f"\n{'='*60}")
    print(f"{'Indicator':<20} {'Latest':>12} {'Date':>12} {'Unit':<15}")
    print(f"{'-'*60}")
    for sid, data in results.items():
        if "error" in data:
            print(f"{sid:<20} {'ERROR':>12}")
            continue
        latest = data.get("latest", {})
        val = latest.get("value", "N/A")
        date = latest.get("date", "N/A")
        units = data.get("units", "")[:15]
        print(f"{sid:<20} {val:>12} {date:>12} {units:<15}")

    # JSON output
    if args.json:
        json_path = DATA_DIR / f"fred_{'_'.join(indicator_ids[:5])}.json"
        json_path.write_text(json.dumps(results, indent=2))
        print(f"\nJSON saved to: {json_path}")

    print(f"\n=== Done: {len(results)} indicators fetched ===")
    return results


if __name__ == "__main__":
    main()
