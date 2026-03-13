#!/usr/bin/env python3
"""Entry point — runs the full daily sentiment cycle.

Usage:
    python -m news_sentiment.run                    # today's date, all tickers
    python -m news_sentiment.run --ticker TSLA      # single ticker
    python -m news_sentiment.run --from 2026-03-10 --to 2026-03-13  # custom range
    python -m news_sentiment.run --skip-macro       # skip macro pipeline
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from news_sentiment.agent import run_company_pipeline, run_macro_pipeline
from news_sentiment.tools.index import compute_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    path = path or _CONFIG_PATH
    with open(path) as f:
        return yaml.safe_load(f)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="News Sentiment Daily Run")
    parser.add_argument("--ticker", type=str, help="Run for a single ticker only")
    parser.add_argument("--from", dest="from_date", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--skip-macro", action="store_true", help="Skip the macro pipeline")
    parser.add_argument("--config", type=str, help="Path to config.yaml")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config) if args.config else None)

    # Date range
    to_date = args.to_date or date.today().isoformat()
    lookback_hours = cfg.get("company_news_lookback_hours", 24)
    from_date = args.from_date or (
        date.fromisoformat(to_date) - timedelta(hours=lookback_hours)
    ).isoformat()

    # Ticker universe
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = cfg.get("tickers", [])

    if not tickers:
        logger.error("No tickers configured. Set --ticker or add to config.yaml.")
        sys.exit(1)

    logger.info("=== News Sentiment Daily Run ===")
    logger.info("Date range: %s to %s", from_date, to_date)
    logger.info("Tickers: %s", ", ".join(tickers))

    # --- Step 1: Macro pipeline (once) ---
    if not args.skip_macro:
        logger.info("--- Running Macro Pipeline ---")
        try:
            macro_result = run_macro_pipeline(from_date, to_date)
            logger.info("Macro pipeline complete.")
            print("\n[MACRO PIPELINE RESULT]")
            print(macro_result)
            print()
        except Exception:
            logger.exception("Macro pipeline failed")
    else:
        logger.info("Skipping macro pipeline (--skip-macro)")

    # --- Step 2: Company pipelines ---
    index_results = []
    for ticker in tickers:
        logger.info("--- Running Company Pipeline: %s ---", ticker)
        try:
            company_result = run_company_pipeline(ticker, from_date, to_date)
            print(f"\n[{ticker} PIPELINE RESULT]")
            print(company_result)
            print()
        except Exception:
            logger.exception("Company pipeline failed for %s", ticker)
            continue

        # --- Step 3: Compute final index ---
        try:
            idx = compute_index(ticker, to_date)
            index_results.append(idx)
        except Exception:
            logger.exception("Index computation failed for %s", ticker)

    # --- Step 4: Summary table ---
    if index_results:
        print("\n" + "=" * 72)
        print(f"{'TICKER':<8} {'INDEX':>8} {'COMPANY':>10} {'MACRO':>10} {'ARTICLES':>10} {'EVENTS':>10}")
        print("-" * 72)
        for idx in index_results:
            print(
                f"{idx['ticker']:<8} "
                f"{idx['index_value']:>+8.4f} "
                f"{idx['company_component']:>+10.4f} "
                f"{idx['macro_component']:>+10.4f} "
                f"{idx['article_count']:>10d} "
                f"{idx['macro_event_count']:>10d}"
            )
        print("=" * 72)

        # Top contributors detail
        for idx in index_results:
            if idx["top_company_contributors"] or idx["top_macro_contributors"]:
                print(f"\n--- {idx['ticker']} Top Contributors ---")
                for c in idx["top_company_contributors"][:3]:
                    print(f"  [Company] {c['contribution']:>+.4f}  ({c['days_old']}d ago)  {c['headline'][:60]}")
                for c in idx["top_macro_contributors"][:3]:
                    print(f"  [Macro]   {c['contribution']:>+.4f}  ({c['days_old']}d ago)  {c['headline'][:60]}")
    else:
        print("\nNo index results to display.")


if __name__ == "__main__":
    main()
