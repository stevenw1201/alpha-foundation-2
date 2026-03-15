"""
Technical Analysis Tool
Computes SMAs, EMAs, RSI, MACD, Bollinger Bands, and OBV from price data.

Usage:
    python tools/technicals.py --ticker AAPL --data data/AAPL_prices.csv
    python tools/technicals.py --ticker TSLA --data '{"dates":["2024-01-02",...],"close":[...],"volume":[...]}'
    python tools/technicals.py --ticker GOOGL --data data/prices.json --chart output/charts/GOOGL_ta.png

Input format (CSV): date,open,high,low,close,volume
Input format (JSON): {"dates":[...], "close":[...], "volume":[...], "high":[...], "low":[...]}

Outputs a structured technical summary to stdout and optionally generates a TA chart.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from dataclasses import dataclass

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
@dataclass
class PriceBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_csv(filepath: str) -> list[PriceBar]:
    bars = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                bars.append(PriceBar(
                    date=row.get("date", row.get("Date", "")),
                    open=float(row.get("open", row.get("Open", 0))),
                    high=float(row.get("high", row.get("High", 0))),
                    low=float(row.get("low", row.get("Low", 0))),
                    close=float(row.get("close", row.get("Close", 0))),
                    volume=float(row.get("volume", row.get("Volume", 0))),
                ))
            except (ValueError, KeyError):
                continue
    return bars


def load_json(data_str: str) -> list[PriceBar]:
    if Path(data_str).exists():
        data = json.loads(Path(data_str).read_text())
    else:
        data = json.loads(data_str)

    dates = data.get("dates", [])
    closes = data.get("close", [])
    volumes = data.get("volume", [0] * len(closes))
    highs = data.get("high", closes)
    lows = data.get("low", closes)
    opens = data.get("open", closes)

    bars = []
    for i in range(len(dates)):
        bars.append(PriceBar(
            date=dates[i],
            open=float(opens[i]) if i < len(opens) else float(closes[i]),
            high=float(highs[i]) if i < len(highs) else float(closes[i]),
            low=float(lows[i]) if i < len(lows) else float(closes[i]),
            close=float(closes[i]),
            volume=float(volumes[i]) if i < len(volumes) else 0,
        ))
    return bars


# ---------------------------------------------------------------------------
# Indicator Calculations
# ---------------------------------------------------------------------------

def sma(closes: list[float], period: int) -> list[float | None]:
    """Simple Moving Average."""
    result = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1:i + 1]) / period
    return result


def ema(closes: list[float], period: int) -> list[float | None]:
    """Exponential Moving Average."""
    result = [None] * len(closes)
    if len(closes) < period:
        return result

    # Seed with SMA
    seed = sum(closes[:period]) / period
    result[period - 1] = seed
    multiplier = 2 / (period + 1)

    for i in range(period, len(closes)):
        result[i] = (closes[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index (Wilder smoothing)."""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100 - (100 / (1 + rs))

    return result


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD: returns (macd_line, signal_line, histogram)."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Signal line = EMA of MACD line
    macd_values = [v for v in macd_line if v is not None]
    if len(macd_values) < signal:
        return macd_line, [None] * len(closes), [None] * len(closes)

    signal_ema = ema(macd_values, signal)

    # Map signal back to full array
    signal_line = [None] * len(closes)
    macd_start = next(i for i, v in enumerate(macd_line) if v is not None)
    for i, val in enumerate(signal_ema):
        if val is not None:
            signal_line[macd_start + i] = val

    # Histogram
    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]

    return macd_line, signal_line, histogram


def bollinger_bands(closes: list[float], period: int = 20, std_dev: float = 2.0):
    """Bollinger Bands: returns (upper, middle/SMA, lower)."""
    middle = sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        mean = middle[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        upper[i] = mean + std_dev * std
        lower[i] = mean - std_dev * std

    return upper, middle, lower


def obv(closes: list[float], volumes: list[float]) -> list[float]:
    """On-Balance Volume."""
    result = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            result.append(result[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            result.append(result[-1] - volumes[i])
        else:
            result.append(result[-1])
    return result


# ---------------------------------------------------------------------------
# Analysis & Summary
# ---------------------------------------------------------------------------

def analyze(bars: list[PriceBar], ticker: str) -> dict:
    """Run full technical analysis and return structured summary."""
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    dates = [b.date for b in bars]

    current = closes[-1]
    prev = closes[-2] if len(closes) > 1 else current

    # Moving Averages
    sma_20 = sma(closes, 20)
    sma_50 = sma(closes, 50)
    sma_100 = sma(closes, 100)
    sma_200 = sma(closes, 200)
    ema_20 = ema(closes, 20)
    ema_50 = ema(closes, 50)

    # Momentum
    rsi_14 = rsi(closes, 14)
    macd_line, signal_line, histogram = macd(closes)
    bb_upper, bb_middle, bb_lower = bollinger_bands(closes)

    # Volume
    obv_values = obv(closes, volumes)

    # Build summary
    def latest(series):
        for v in reversed(series):
            if v is not None:
                return v
        return None

    sma_50_val = latest(sma_50)
    sma_100_val = latest(sma_100)
    ema_20_val = latest(ema_20)
    ema_50_val = latest(ema_50)
    rsi_val = latest(rsi_14)
    macd_val = latest(macd_line)
    signal_val = latest(signal_line)
    hist_val = latest(histogram)
    bb_up = latest(bb_upper)
    bb_low = latest(bb_lower)
    bb_mid = latest(bb_middle)

    # Trend determination
    trend = "NEUTRAL"
    if sma_50_val and sma_100_val:
        if current > sma_50_val > sma_100_val:
            trend = "BULLISH"
        elif current < sma_50_val < sma_100_val:
            trend = "BEARISH"
        elif current > sma_50_val:
            trend = "MILDLY BULLISH"
        elif current < sma_50_val:
            trend = "MILDLY BEARISH"

    # RSI interpretation
    rsi_signal = "NEUTRAL"
    if rsi_val:
        if rsi_val > 70:
            rsi_signal = "OVERBOUGHT"
        elif rsi_val < 30:
            rsi_signal = "OVERSOLD"
        elif rsi_val > 60:
            rsi_signal = "BULLISH MOMENTUM"
        elif rsi_val < 40:
            rsi_signal = "BEARISH MOMENTUM"

    # MACD interpretation
    macd_signal = "NEUTRAL"
    if macd_val is not None and signal_val is not None:
        if macd_val > signal_val and hist_val and hist_val > 0:
            macd_signal = "BULLISH CROSSOVER" if abs(macd_val - signal_val) < 0.5 else "BULLISH"
        elif macd_val < signal_val and hist_val and hist_val < 0:
            macd_signal = "BEARISH CROSSOVER" if abs(macd_val - signal_val) < 0.5 else "BEARISH"

    # Bollinger Band position
    bb_position = "MIDDLE"
    if bb_up and bb_low:
        bb_width = bb_up - bb_low
        if bb_width > 0:
            position_pct = (current - bb_low) / bb_width
            if position_pct > 0.95:
                bb_position = "UPPER BAND (potential mean reversion)"
            elif position_pct < 0.05:
                bb_position = "LOWER BAND (potential bounce)"
            elif position_pct > 0.75:
                bb_position = "UPPER HALF"
            elif position_pct < 0.25:
                bb_position = "LOWER HALF"

    # OBV trend
    obv_trend = "FLAT"
    if len(obv_values) >= 20:
        obv_recent = obv_values[-20:]
        obv_sma = sum(obv_recent) / len(obv_recent)
        if obv_values[-1] > obv_sma * 1.02:
            obv_trend = "ACCUMULATION"
        elif obv_values[-1] < obv_sma * 0.98:
            obv_trend = "DISTRIBUTION"

    summary = {
        "ticker": ticker,
        "current_price": current,
        "date": dates[-1],
        "data_points": len(bars),
        "trend": {
            "overall": trend,
            "sma_50": round(sma_50_val, 2) if sma_50_val else None,
            "sma_100": round(sma_100_val, 2) if sma_100_val else None,
            "ema_20": round(ema_20_val, 2) if ema_20_val else None,
            "ema_50": round(ema_50_val, 2) if ema_50_val else None,
            "price_vs_sma50": f"{((current / sma_50_val - 1) * 100):.1f}%" if sma_50_val else None,
            "price_vs_sma100": f"{((current / sma_100_val - 1) * 100):.1f}%" if sma_100_val else None,
        },
        "momentum": {
            "rsi_14": round(rsi_val, 1) if rsi_val else None,
            "rsi_signal": rsi_signal,
            "macd": round(macd_val, 4) if macd_val else None,
            "macd_signal_line": round(signal_val, 4) if signal_val else None,
            "macd_histogram": round(hist_val, 4) if hist_val else None,
            "macd_signal": macd_signal,
        },
        "volatility": {
            "bb_upper": round(bb_up, 2) if bb_up else None,
            "bb_middle": round(bb_mid, 2) if bb_mid else None,
            "bb_lower": round(bb_low, 2) if bb_low else None,
            "bb_position": bb_position,
            "bb_width_pct": f"{((bb_up - bb_low) / bb_mid * 100):.1f}%" if bb_up and bb_low and bb_mid else None,
        },
        "volume": {
            "obv_trend": obv_trend,
            "confirms_price": (
                (obv_trend == "ACCUMULATION" and trend in ("BULLISH", "MILDLY BULLISH")) or
                (obv_trend == "DISTRIBUTION" and trend in ("BEARISH", "MILDLY BEARISH")) or
                obv_trend == "FLAT"
            ),
        },
    }

    return summary


def print_summary(s: dict):
    """Pretty-print the technical analysis summary."""
    print(f"\n{'='*60}")
    print(f"  TECHNICAL ANALYSIS: {s['ticker']}")
    print(f"  Price: ${s['current_price']:.2f} | Date: {s['date']} | Data: {s['data_points']} bars")
    print(f"{'='*60}")

    t = s["trend"]
    print(f"\n  TREND: {t['overall']}")
    print(f"    50-day SMA:  ${t['sma_50']}" if t['sma_50'] else "    50-day SMA:  N/A")
    print(f"    100-day SMA: ${t['sma_100']}" if t['sma_100'] else "    100-day SMA: N/A")
    print(f"    20-day EMA:  ${t['ema_20']}" if t['ema_20'] else "    20-day EMA:  N/A")
    print(f"    50-day EMA:  ${t['ema_50']}" if t['ema_50'] else "    50-day EMA:  N/A")
    if t['price_vs_sma50']:
        print(f"    Price vs SMA50:  {t['price_vs_sma50']}")
    if t['price_vs_sma100']:
        print(f"    Price vs SMA100: {t['price_vs_sma100']}")

    m = s["momentum"]
    print(f"\n  MOMENTUM:")
    print(f"    RSI(14):     {m['rsi_14']} → {m['rsi_signal']}")
    print(f"    MACD:        {m['macd']} | Signal: {m['macd_signal_line']} | Hist: {m['macd_histogram']}")
    print(f"    MACD Signal: {m['macd_signal']}")

    v = s["volatility"]
    print(f"\n  VOLATILITY (Bollinger Bands):")
    print(f"    Upper: ${v['bb_upper']} | Mid: ${v['bb_middle']} | Lower: ${v['bb_lower']}")
    print(f"    Position: {v['bb_position']}")
    if v['bb_width_pct']:
        print(f"    Band Width: {v['bb_width_pct']}")

    vol = s["volume"]
    print(f"\n  VOLUME:")
    print(f"    OBV Trend: {vol['obv_trend']}")
    print(f"    Confirms Price: {'YES' if vol['confirms_price'] else 'NO — DIVERGENCE'}")
    print(f"\n{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Technical Analysis Tool")
    parser.add_argument("--ticker", required=True, help="Stock ticker")
    parser.add_argument("--data", required=True, help="CSV file, JSON file, or JSON string")
    parser.add_argument("--chart", default=None, help="Output path for TA chart (PNG)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Load data
    if args.data.endswith(".csv"):
        bars = load_csv(args.data)
    else:
        bars = load_json(args.data)

    if len(bars) < 30:
        print(f"WARNING: Only {len(bars)} bars loaded. Need 100+ for reliable analysis.")
    if not bars:
        print("ERROR: No price data loaded.")
        sys.exit(1)

    print(f"Loaded {len(bars)} price bars for {args.ticker}")

    # Analyze
    summary = analyze(bars, args.ticker)
    print_summary(summary)

    if args.json:
        out_path = Path("data") / f"{args.ticker}_technicals.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2))
        print(f"JSON saved: {out_path}")

    return summary


if __name__ == "__main__":
    main()
