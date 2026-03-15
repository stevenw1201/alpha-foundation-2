"""
SEC EDGAR Filing Retrieval Tool
Pulls filings (10-K, 10-Q, 8-K, DEF 14A) for a given ticker.
Uses the EDGAR full-text search API and company filings API.

Usage:
    python tools/edgar.py --ticker AAPL --filings 10-K,10-Q --years 5
    python tools/edgar.py --ticker TSLA --filings 10-K --years 3 --sections "Item 7,Item 8"
    python tools/edgar.py --ticker GOOGL --search "revenue recognition"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests --break-system-packages")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "https://efts.sec.gov/LATEST"
COMPANY_URL = "https://data.sec.gov"
HEADERS = {
    "User-Agent": "EquityResearchAgent/1.0 (12wangjiahao@gmail.com)",
    "Accept": "application/json",
}
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "edgar"
RATE_LIMIT_DELAY = 0.15  # SEC rate limit: 10 req/sec


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_cik(ticker: str) -> str | None:
    """Resolve ticker to zero-padded CIK via SEC company tickers JSON."""
    cache_path = DATA_DIR / "company_tickers.json"
    if not cache_path.exists() or (time.time() - cache_path.stat().st_mtime > 86400):
        url = f"{COMPANY_URL}/files/company_tickers.json"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        cache_path.write_text(resp.text)
        time.sleep(RATE_LIMIT_DELAY)

    tickers = json.loads(cache_path.read_text())
    ticker_upper = ticker.upper()
    for entry in tickers.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    return None


def get_company_facts(cik: str) -> dict | None:
    """Pull the full company facts (XBRL) for financial data extraction."""
    cache_path = DATA_DIR / f"facts_{cik}.json"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime < 3600):
        return json.loads(cache_path.read_text())

    url = f"{COMPANY_URL}/api/xbrl/companyfacts/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    time.sleep(RATE_LIMIT_DELAY)
    if resp.status_code != 200:
        print(f"WARNING: Could not fetch company facts for CIK {cik}: {resp.status_code}")
        return None
    data = resp.json()
    cache_path.write_text(json.dumps(data))
    return data


def get_filings_index(cik: str, filing_types: list[str], years: int) -> list[dict]:
    """Get filing index from EDGAR submissions API."""
    url = f"{COMPANY_URL}/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    time.sleep(RATE_LIMIT_DELAY)

    submissions = resp.json()
    recent = submissions.get("filings", {}).get("recent", {})

    cutoff = datetime.now() - timedelta(days=years * 365)
    results = []

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    for i in range(len(forms)):
        form = forms[i]
        if form not in filing_types:
            continue
        filing_date = datetime.strptime(dates[i], "%Y-%m-%d")
        if filing_date < cutoff:
            continue

        accession_clean = accessions[i].replace("-", "")
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik.lstrip('0')}/{accession_clean}/{primary_docs[i]}"
        )

        results.append({
            "form": form,
            "date": dates[i],
            "accession": accessions[i],
            "url": doc_url,
        })

    return results


def extract_xbrl_financials(facts: dict, years: int) -> dict:
    """Extract key financial metrics from XBRL company facts."""
    cutoff_year = datetime.now().year - years
    metrics_map = {
        "Revenue": [
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:SalesRevenueNet",
        ],
        "GrossProfit": ["us-gaap:GrossProfit"],
        "OperatingIncome": [
            "us-gaap:OperatingIncomeLoss",
            "us-gaap:IncomeLossFromContinuingOperations",
        ],
        "NetIncome": [
            "us-gaap:NetIncomeLoss",
            "us-gaap:ProfitLoss",
        ],
        "EBITDA": [],  # Typically not in XBRL; compute from components if needed
        "TotalAssets": ["us-gaap:Assets"],
        "TotalLiabilities": ["us-gaap:Liabilities"],
        "CashAndEquivalents": [
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            "us-gaap:Cash",
        ],
        "SharesOutstanding": [
            "us-gaap:CommonStockSharesOutstanding",
            "dei:EntityCommonStockSharesOutstanding",
        ],
    }

    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})
    combined = {**{f"us-gaap:{k}": v for k, v in us_gaap.items()},
                **{f"dei:{k}": v for k, v in dei.items()}}

    extracted = {}
    for label, concept_keys in metrics_map.items():
        for key in concept_keys:
            concept = combined.get(key.split(":")[-1] if ":" in key else key)
            if not concept:
                # Try the full key
                concept = combined.get(key)
            if not concept:
                continue

            units = concept.get("units", {})
            # Try USD first, then shares, then pure
            values = units.get("USD", units.get("shares", units.get("pure", [])))
            if not values:
                continue

            # Filter to annual (10-K) filings within the year range
            annual = []
            for v in values:
                fp = v.get("fp", "")
                fy = v.get("fy", 0)
                form = v.get("form", "")
                if form == "10-K" and fy >= cutoff_year:
                    annual.append({
                        "year": fy,
                        "value": v["val"],
                        "filed": v.get("filed", ""),
                    })

            if annual:
                # Deduplicate by year, keep latest filed
                by_year = {}
                for a in annual:
                    y = a["year"]
                    if y not in by_year or a["filed"] > by_year[y]["filed"]:
                        by_year[y] = a
                extracted[label] = dict(sorted(by_year.items()))
                break

    return extracted


def search_filings(ticker: str, query: str, years: int) -> list[dict]:
    """Full-text search across EDGAR filings."""
    date_from = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    url = (
        f"{BASE_URL}/search-index?q={quote(query)}"
        f"&dateRange=custom&startdt={date_from}"
        f"&enddt={datetime.now().strftime('%Y-%m-%d')}"
        f"&forms=10-K,10-Q,8-K"
    )

    # Try ticker filter
    resp = requests.get(url + f"&q={quote(query + ' ' + ticker)}", headers=HEADERS, timeout=15)
    time.sleep(RATE_LIMIT_DELAY)

    if resp.status_code != 200:
        return []

    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])
    return [
        {
            "form": h["_source"].get("form_type", ""),
            "date": h["_source"].get("file_date", ""),
            "entity": h["_source"].get("entity_name", ""),
            "description": h["_source"].get("file_description", ""),
        }
        for h in hits[:10]
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="SEC EDGAR Filing Retrieval")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--filings", default="10-K,10-Q", help="Comma-separated filing types")
    parser.add_argument("--years", type=int, default=5, help="Lookback period in years")
    parser.add_argument("--sections", default=None, help="Comma-separated 10-K sections to extract")
    parser.add_argument("--search", default=None, help="Full-text search query across filings")
    parser.add_argument("--financials", action="store_true", help="Extract XBRL financial data")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    ensure_data_dir()

    ticker = args.ticker.upper()
    print(f"=== EDGAR Lookup: {ticker} ===\n")

    # Resolve CIK
    cik = get_cik(ticker)
    if not cik:
        print(f"ERROR: Could not resolve CIK for ticker '{ticker}'")
        sys.exit(1)
    print(f"CIK: {cik}")

    output = {"ticker": ticker, "cik": cik}

    # Full-text search mode
    if args.search:
        print(f"\nSearching filings for: '{args.search}'")
        results = search_filings(ticker, args.search, args.years)
        output["search_results"] = results
        for r in results:
            print(f"  [{r['form']}] {r['date']} — {r['entity']}: {r['description']}")

    # Filing index
    filing_types = [f.strip() for f in args.filings.split(",")]
    print(f"\nFetching filing index: {filing_types} (last {args.years} years)")
    filings = get_filings_index(cik, filing_types, args.years)
    output["filings"] = filings
    for f in filings:
        print(f"  [{f['form']}] {f['date']} — {f['url']}")

    # XBRL financial extraction
    if args.financials:
        print(f"\nExtracting XBRL financials...")
        facts = get_company_facts(cik)
        if facts:
            financials = extract_xbrl_financials(facts, args.years)
            output["financials"] = financials
            for metric, years_data in financials.items():
                print(f"\n  {metric}:")
                for yr, info in years_data.items():
                    val = info["value"]
                    if abs(val) >= 1e9:
                        print(f"    {yr}: ${val/1e9:.2f}B")
                    elif abs(val) >= 1e6:
                        print(f"    {yr}: ${val/1e6:.2f}M")
                    else:
                        print(f"    {yr}: {val:,.0f}")
        else:
            print("  WARNING: XBRL data unavailable for this company")

    # JSON output
    if args.json:
        json_path = DATA_DIR / f"{ticker}_edgar.json"
        json_path.write_text(json.dumps(output, indent=2, default=str))
        print(f"\nJSON saved to: {json_path}")

    print(f"\n=== Done: {len(filings)} filings found ===")
    return output


if __name__ == "__main__":
    main()
