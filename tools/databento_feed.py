"""
Databento Data Feed — NASDAQ TotalView (XNAS.ITCH)
Pulls OHLCV bars, trades, and book data for equity research.

Usage:
    # Daily OHLCV bars (default for research reports)
    python tools/databento_feed.py --ticker AAPL --bars daily --days 365

    # Minute bars for intraday context
    python tools/databento_feed.py --ticker TSLA --bars 1min --days 30

    # Multiple tickers (peer comparison)
    python tools/databento_feed.py --tickers AAPL,MSFT,GOOGL --bars daily --days 365

    # Pipe directly to technicals
    python tools/databento_feed.py --ticker NVDA --bars daily --days 250 --output data/NVDA_prices.csv
    python tools/technicals.py --ticker NVDA --data data/NVDA_prices.csv

    # Export for charts tool
    python tools/databento_feed.py --ticker AAPL --bars daily --days 365 --format json --output data/AAPL_prices.json

Requires DATABENTO_API_KEY environment variable.
Get one at: https://databento.com/signup

Dataset: XNAS.ITCH (NASDAQ TotalView)
- Full depth-of-book (L2/L3) available
- Trade + quote data from NASDAQ exchange
- Covers all NASDAQ-listed securities
- For NYSE-listed tickers, use XNYS.PILLAR or add SIP (DBEQ.MAX) as fallback
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import databento as db
except ImportError:
    db = None
    print("WARNING: databento not installed. Run: pip install databento --break-system-packages")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "prices"
CACHE_TTL = 900  # 15 min cache for intraday, daily cache is longer

# Dataset routing: prefer NASDAQ TotalView, fallback for non-NASDAQ listings
DATASET_MAP = {
    "primary": "XNAS.ITCH",        # NASDAQ TotalView — L2 depth, trades
    "nyse_fallback": "XNYS.PILLAR",  # NYSE Pillar — for NYSE-listed
    "sip_fallback": "DBEQ.MAX",      # SIP consolidated — universal fallback
}

# Schema mapping for Databento
SCHEMA_MAP = {
    "daily": "ohlcv-1d",
    "1h": "ohlcv-1h",
    "1min": "ohlcv-1m",
    "1s": "ohlcv-1s",
    "trades": "trades",
    "mbp1": "mbp-1",     # Top of book
    "mbp10": "mbp-10",   # 10-level depth
}

# Common NASDAQ-listed tickers (for dataset routing)
# In production, resolve via symbology API
NASDAQ_LISTED = {
    "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "NVDA",
    "AVGO", "COST", "NFLX", "AMD", "ADBE", "INTC", "CSCO", "CMCSA",
    "PEP", "TMUS", "TXN", "AMGN", "ISRG", "INTU", "QCOM", "AMAT",
    "HON", "BKNG", "SBUX", "MDLZ", "GILD", "ADI", "LRCX", "REGN",
    "VRTX", "PANW", "KLAC", "MRVL", "PYPL", "SNPS", "CDNS", "CRWD",
    "ABNB", "FTNT", "MELI", "MNST", "DASH", "ORLY", "CTAS", "MAR",
    "PLTR", "HOOD", "CVNA", "COIN", "DDOG", "ZS", "NET",
}


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_api_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY", "")
    if not key:
        print("ERROR: DATABENTO_API_KEY not set.")
        print("Get one at: https://databento.com/signup")
        print("Set it: export DATABENTO_API_KEY='your_key_here'")
    return key


def resolve_dataset(ticker: str) -> str:
    """Route to the correct dataset based on listing exchange."""
    if ticker.upper() in NASDAQ_LISTED:
        return DATASET_MAP["primary"]
    # For unknown tickers, try NASDAQ first (most tech/growth names)
    # Claude Code can retry with fallback if needed
    return DATASET_MAP["primary"]


def get_cache_path(ticker: str, schema: str, days: int) -> Path:
    return DATA_DIR / f"{ticker}_{schema}_{days}d.csv"


def check_cache(cache_path: Path, ttl: int) -> bool:
    if not cache_path.exists():
        return False
    age = time.time() - cache_path.stat().st_mtime
    return age < ttl


def fetch_ohlcv(
    ticker: str,
    schema: str = "ohlcv-1d",
    days: int = 365,
    dataset: str | None = None,
) -> dict:
    """
    Fetch OHLCV bars from Databento.
    Returns dict with dates, open, high, low, close, volume arrays.
    """
    api_key = get_api_key()
    if not api_key:
        return {"error": "No API key"}

    if db is None:
        return {"error": "databento package not installed"}

    if dataset is None:
        dataset = resolve_dataset(ticker)

    end = datetime.now()
    start = end - timedelta(days=days)

    cache_path = get_cache_path(ticker, schema, days)
    cache_ttl = 86400 if "1d" in schema else CACHE_TTL

    if check_cache(cache_path, cache_ttl) and HAS_PANDAS:
        print(f"  Using cached data: {cache_path}")
        df = pd.read_csv(cache_path)
        return dataframe_to_dict(df)

    print(f"  Fetching {ticker} from {dataset} ({schema}, {days}d)...")

    try:
        client = db.Historical(key=api_key)

        data = client.timeseries.get_range(
            dataset=dataset,
            symbols=[ticker],
            schema=schema,
            start=start.strftime("%Y-%m-%dT00:00:00"),
            end=end.strftime("%Y-%m-%dT00:00:00"),
            stype_in="raw_symbol",  # Use raw ticker
        )

        # Convert to DataFrame if pandas available
        if HAS_PANDAS:
            df = data.to_df()

            if df.empty:
                # Try SIP fallback
                if dataset != DATASET_MAP["sip_fallback"]:
                    print(f"  No data on {dataset}, trying SIP fallback...")
                    return fetch_ohlcv(ticker, schema, days, DATASET_MAP["sip_fallback"])
                return {"error": f"No data found for {ticker}"}

            # Normalize column names
            df = normalize_ohlcv_df(df, schema)

            # Cache
            df.to_csv(cache_path, index=False)
            print(f"  Cached: {cache_path} ({len(df)} bars)")

            return dataframe_to_dict(df)
        else:
            # Without pandas, convert manually
            return records_to_dict(data, schema)

    except Exception as e:
        error_msg = str(e)
        print(f"  ERROR: {error_msg}")

        # If NASDAQ dataset fails, try SIP fallback
        if dataset != DATASET_MAP["sip_fallback"] and "not found" in error_msg.lower():
            print(f"  Retrying with SIP fallback ({DATASET_MAP['sip_fallback']})...")
            return fetch_ohlcv(ticker, schema, days, DATASET_MAP["sip_fallback"])

        # Try cache even if expired
        if cache_path.exists():
            print(f"  Falling back to stale cache: {cache_path}")
            if HAS_PANDAS:
                df = pd.read_csv(cache_path)
                return dataframe_to_dict(df)

        return {"error": error_msg}


def normalize_ohlcv_df(df, schema: str):
    """Normalize Databento OHLCV DataFrame to standard columns."""
    # Databento OHLCV columns: ts_event, open, high, low, close, volume
    col_map = {}

    # Handle timestamp
    if "ts_event" in df.columns:
        df["date"] = df["ts_event"].apply(
            lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime")
            else str(x)[:10]
        )
    elif df.index.name and "time" in df.index.name.lower():
        df["date"] = df.index.map(
            lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime")
            else str(x)[:10]
        )
        df = df.reset_index(drop=True)

    # Databento prices are in fixed-point (1e-9 multiplier for some schemas)
    # OHLCV schemas return prices in USD directly
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            # Convert from fixed-point if needed (Databento uses int64 prices)
            if df[col].dtype in ("int64", "int32"):
                df[col] = df[col] / 1e9  # Databento fixed-point convention

    # Keep only what we need
    keep_cols = ["date", "open", "high", "low", "close", "volume"]
    available = [c for c in keep_cols if c in df.columns]
    return df[available]


def dataframe_to_dict(df) -> dict:
    """Convert DataFrame to the dict format technicals.py expects."""
    result = {
        "dates": df["date"].tolist() if "date" in df.columns else [],
        "open": df["open"].tolist() if "open" in df.columns else [],
        "high": df["high"].tolist() if "high" in df.columns else [],
        "low": df["low"].tolist() if "low" in df.columns else [],
        "close": df["close"].tolist() if "close" in df.columns else [],
        "volume": df["volume"].tolist() if "volume" in df.columns else [],
    }
    result["count"] = len(result["dates"])
    return result


def records_to_dict(data, schema: str) -> dict:
    """Convert Databento records to dict without pandas."""
    result = {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
    for record in data:
        ts = getattr(record, "ts_event", None)
        if ts:
            date_str = datetime.utcfromtimestamp(ts / 1e9).strftime("%Y-%m-%d")
        else:
            date_str = ""
        result["dates"].append(date_str)
        result["open"].append(getattr(record, "open", 0) / 1e9)
        result["high"].append(getattr(record, "high", 0) / 1e9)
        result["low"].append(getattr(record, "low", 0) / 1e9)
        result["close"].append(getattr(record, "close", 0) / 1e9)
        result["volume"].append(getattr(record, "volume", 0))
    result["count"] = len(result["dates"])
    return result


def fetch_trades(ticker: str, days: int = 1, dataset: str | None = None) -> dict:
    """Fetch raw trade data — useful for volume analysis and VWAP."""
    api_key = get_api_key()
    if not api_key or db is None:
        return {"error": "No API key or databento not installed"}

    if dataset is None:
        dataset = resolve_dataset(ticker)

    end = datetime.now()
    start = end - timedelta(days=days)

    try:
        client = db.Historical(key=api_key)
        data = client.timeseries.get_range(
            dataset=dataset,
            symbols=[ticker],
            schema="trades",
            start=start.strftime("%Y-%m-%dT00:00:00"),
            end=end.strftime("%Y-%m-%dT00:00:00"),
            stype_in="raw_symbol",
        )

        if HAS_PANDAS:
            df = data.to_df()
            return {
                "ticker": ticker,
                "trade_count": len(df),
                "dataset": dataset,
                "period": f"{days}d",
            }

        return {"ticker": ticker, "dataset": dataset}

    except Exception as e:
        return {"error": str(e)}


def get_book_snapshot(ticker: str, levels: int = 10, dataset: str | None = None) -> dict:
    """
    Fetch latest book snapshot — NASDAQ TotalView L2 depth.
    Useful for gauging institutional interest and liquidity.
    """
    api_key = get_api_key()
    if not api_key or db is None:
        return {"error": "No API key or databento not installed"}

    if dataset is None:
        dataset = resolve_dataset(ticker)

    schema = f"mbp-{levels}"

    try:
        client = db.Historical(key=api_key)
        # Get last trading day's close snapshot
        end = datetime.now()
        start = end - timedelta(days=2)

        data = client.timeseries.get_range(
            dataset=dataset,
            symbols=[ticker],
            schema=schema,
            start=start.strftime("%Y-%m-%dT00:00:00"),
            end=end.strftime("%Y-%m-%dT00:00:00"),
            stype_in="raw_symbol",
            limit=1,  # Just the latest
        )

        return {
            "ticker": ticker,
            "depth_levels": levels,
            "dataset": dataset,
            "schema": schema,
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Multi-ticker batch for peer comparison
# ---------------------------------------------------------------------------

def fetch_peer_ohlcv(
    tickers: list[str],
    schema: str = "ohlcv-1d",
    days: int = 365,
) -> dict[str, dict]:
    """Fetch OHLCV for multiple tickers — used in peer comparison."""
    results = {}
    for ticker in tickers:
        print(f"\nFetching {ticker}...")
        results[ticker] = fetch_ohlcv(ticker, schema, days)
        time.sleep(0.1)  # Rate limit courtesy
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Databento Data Feed — NASDAQ TotalView (XNAS.ITCH)"
    )
    parser.add_argument("--ticker", default=None, help="Single stock ticker")
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers for batch")
    parser.add_argument(
        "--bars", default="daily",
        choices=["daily", "1h", "1min", "1s"],
        help="Bar interval"
    )
    parser.add_argument("--days", type=int, default=365, help="Lookback in days")
    parser.add_argument(
        "--dataset", default=None,
        help=f"Override dataset (default: auto-route). Options: {', '.join(DATASET_MAP.values())}"
    )
    parser.add_argument(
        "--format", default="csv", choices=["csv", "json"],
        help="Output format"
    )
    parser.add_argument("--output", default=None, help="Output file path (auto-generated if omitted)")
    parser.add_argument("--trades", action="store_true", help="Fetch raw trades instead of OHLCV")
    parser.add_argument("--book", action="store_true", help="Fetch book snapshot")
    parser.add_argument("--book-levels", type=int, default=10, help="Book depth levels (1 or 10)")

    args = parser.parse_args()
    ensure_data_dir()

    # Determine tickers
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        print("ERROR: Provide --ticker or --tickers")
        parser.print_help()
        sys.exit(1)

    schema = SCHEMA_MAP.get(args.bars, "ohlcv-1d")

    print(f"=== Databento Feed ===")
    print(f"Tickers:  {', '.join(tickers)}")
    print(f"Schema:   {schema}")
    print(f"Lookback: {args.days} days")
    print(f"Dataset:  {args.dataset or 'auto-route'}")

    # Book snapshot mode
    if args.book:
        for t in tickers:
            result = get_book_snapshot(t, args.book_levels, args.dataset)
            print(f"\n{t} Book Snapshot: {json.dumps(result, indent=2)}")
        return

    # Trades mode
    if args.trades:
        for t in tickers:
            result = fetch_trades(t, args.days, args.dataset)
            print(f"\n{t} Trades: {json.dumps(result, indent=2)}")
        return

    # OHLCV mode (default)
    for t in tickers:
        result = fetch_ohlcv(t, schema, args.days, args.dataset)

        if "error" in result:
            print(f"\n{t}: ERROR — {result['error']}")
            continue

        count = result.get("count", 0)
        print(f"\n{t}: {count} bars retrieved")

        if count > 0:
            latest_close = result["close"][-1]
            first_close = result["close"][0]
            pct_change = ((latest_close / first_close) - 1) * 100 if first_close else 0
            print(f"  First: ${first_close:.2f} ({result['dates'][0]})")
            print(f"  Last:  ${latest_close:.2f} ({result['dates'][-1]})")
            print(f"  Change: {pct_change:+.1f}%")

        # Save output
        out_path = args.output
        if not out_path:
            ext = "json" if args.format == "json" else "csv"
            out_path = str(DATA_DIR / f"{t}_{args.bars}_{args.days}d.{ext}")

        if args.format == "json":
            Path(out_path).write_text(json.dumps(result, indent=2))
        else:
            # CSV output compatible with technicals.py
            if HAS_PANDAS:
                import pandas as _pd
                df = _pd.DataFrame({
                    "date": result["dates"],
                    "open": result["open"],
                    "high": result["high"],
                    "low": result["low"],
                    "close": result["close"],
                    "volume": result["volume"],
                })
                df.to_csv(out_path, index=False)
            else:
                import csv
                with open(out_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["date", "open", "high", "low", "close", "volume"])
                    for i in range(len(result["dates"])):
                        writer.writerow([
                            result["dates"][i],
                            result["open"][i],
                            result["high"][i],
                            result["low"][i],
                            result["close"][i],
                            result["volume"][i],
                        ])

        print(f"  Saved: {out_path}")

    print(f"\n=== Done ===")


if __name__ == "__main__":
    main()
