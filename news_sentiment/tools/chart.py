"""Generate sentiment index charts for research notes.

Two chart functions:
- generate_index_chart  — per-ticker time series with decomposition
- generate_universe_summary — horizontal bar chart ranking all tickers
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np

from news_sentiment.tools.storage import load_index_history

_BASE_DIR = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _BASE_DIR / "output"

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
_BLUE = "#1f77b4"
_BLUE_LIGHT = "#aec7e8"
_AMBER = "#e8910d"
_AMBER_LIGHT = "#ffd699"
_GREEN = "#2ca02c"
_RED = "#d62728"
_GRAY = "#888888"
_INDEX_COLOR = "#1a1a2e"


def generate_index_chart(
    ticker: str,
    days: int = 14,
    *,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
) -> str | None:
    """Generate a sentiment index time-series chart for *ticker*.

    Args:
        ticker: Uppercase stock ticker.
        days: Number of days of history to plot.
        data_dir: Override data directory.
        output_dir: Override output directory.

    Returns:
        Path to the saved PNG, or None if no data.
    """
    data_dir = Path(data_dir) if data_dir else (_BASE_DIR / "data")
    output_dir = Path(output_dir) if output_dir else _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    history = load_index_history(ticker, data_dir=data_dir)
    if not history:
        return None

    # Trim to requested window
    history = history[-days:]

    dates = [datetime.fromisoformat(r["as_of_date"]) for r in history]
    index_vals = np.array([r["index_value"] for r in history])
    company_vals = np.array([r["company_component"] for r in history])
    macro_vals = np.array([r["macro_component"] for r in history])

    # --- Figure setup ---
    fig, ax = plt.subplots(figsize=(12, 5.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # --- Stacked area: company + macro decomposition ---
    # Plot company and macro as separate filled areas from the zero line
    ax.fill_between(
        dates, 0, company_vals,
        alpha=0.35, color=_BLUE, label="Company",
        step="mid",
    )
    ax.fill_between(
        dates, 0, macro_vals,
        alpha=0.35, color=_AMBER, label="Macro",
        step="mid",
    )

    # --- Index line (prominent) ---
    ax.plot(
        dates, index_vals,
        color=_INDEX_COLOR, linewidth=2.2, zorder=5,
        marker="o", markersize=4, label="Index",
    )

    # --- Shade positive/negative regions on the index line ---
    ax.fill_between(
        dates, 0, index_vals,
        where=index_vals >= 0, alpha=0.08, color=_GREEN,
        interpolate=True,
    )
    ax.fill_between(
        dates, 0, index_vals,
        where=index_vals < 0, alpha=0.08, color=_RED,
        interpolate=True,
    )

    # --- Zero line ---
    ax.axhline(0, color=_GRAY, linewidth=0.8, linestyle="--", zorder=1)

    # --- Annotate top contributors ---
    _annotate_top_contributors(ax, history, dates, index_vals)

    # --- Formatting ---
    latest = history[-1]
    ax.set_title(
        f"{ticker} News Sentiment Index",
        fontsize=15, fontweight="bold", pad=18, loc="left",
    )
    ax.text(
        0.0, 1.02,
        (
            f"Current: {latest['index_value']:+.3f}  "
            f"(Company: {latest['company_component']:+.3f} | "
            f"Macro: {latest['macro_component']:+.3f})"
        ),
        transform=ax.transAxes,
        fontsize=9, color=_GRAY, va="bottom",
    )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(dates) // 8)))
    fig.autofmt_xdate(rotation=30, ha="right")

    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%+.2f"))
    ax.grid(axis="y", alpha=0.2, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.3)
    ax.spines["bottom"].set_alpha(0.3)

    ax.legend(
        loc="upper left", frameon=False, fontsize=8,
        ncol=3, borderpad=0.5,
    )

    fig.tight_layout()

    out_path = output_dir / f"{ticker}_sentiment_{date.today().isoformat()}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return str(out_path)


def _annotate_top_contributors(
    ax, history: list[dict], dates: list, index_vals: np.ndarray,
) -> None:
    """Add small text annotations for the biggest single-day movers."""
    # Find dates with the largest absolute index values (up to 3)
    abs_vals = np.abs(index_vals)
    n_annotations = min(3, len(history))
    top_indices = np.argsort(abs_vals)[-n_annotations:]

    for i in top_indices:
        entry = history[i]
        # Pick the top company or macro contributor headline
        headline = None
        for contrib_key in ("top_company_contributors", "top_macro_contributors"):
            contribs = entry.get(contrib_key, [])
            if contribs:
                headline = contribs[0].get("headline", "")
                break
        if not headline:
            continue

        # Truncate headline
        label = headline[:45] + "..." if len(headline) > 45 else headline
        val = index_vals[i]

        ax.annotate(
            label,
            xy=(dates[i], val),
            xytext=(0, 14 if val >= 0 else -14),
            textcoords="offset points",
            fontsize=6.5,
            color=_GRAY,
            ha="center",
            va="bottom" if val >= 0 else "top",
            arrowprops=dict(
                arrowstyle="-",
                color=_GRAY,
                linewidth=0.5,
            ),
        )


def generate_universe_summary(
    tickers: list[str],
    as_of_date: str,
    *,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
) -> str | None:
    """Generate a horizontal bar chart showing all tickers ranked by index value.

    Args:
        tickers: List of uppercase stock tickers.
        as_of_date: The date to show (YYYY-MM-DD). Uses the latest entry
            on or before this date for each ticker.
        data_dir: Override data directory.
        output_dir: Override output directory.

    Returns:
        Path to the saved PNG, or None if no data.
    """
    data_dir = Path(data_dir) if data_dir else (_BASE_DIR / "data")
    output_dir = Path(output_dir) if output_dir else _OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect latest index result per ticker
    rows: list[dict] = []
    for ticker in tickers:
        history = load_index_history(ticker, data_dir=data_dir)
        if not history:
            continue
        # Find latest entry on or before as_of_date
        candidates = [r for r in history if r["as_of_date"] <= as_of_date]
        if candidates:
            rows.append(candidates[-1])

    if not rows:
        return None

    # Sort by index_value
    rows.sort(key=lambda r: r["index_value"])

    ticker_labels = [r["ticker"] for r in rows]
    company_vals = np.array([r["company_component"] for r in rows])
    macro_vals = np.array([r["macro_component"] for r in rows])
    index_vals = np.array([r["index_value"] for r in rows])

    # --- Figure ---
    n = len(rows)
    fig_height = max(3, n * 0.55 + 1.5)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    y_pos = np.arange(n)
    bar_height = 0.55

    # Company component bars
    ax.barh(
        y_pos, company_vals, height=bar_height,
        color=_BLUE, alpha=0.75, label="Company",
    )
    # Macro component bars (stacked from company)
    ax.barh(
        y_pos, macro_vals, height=bar_height,
        left=company_vals, color=_AMBER, alpha=0.75, label="Macro",
    )

    # Value labels at bar tips
    for i, (idx_val, ticker) in enumerate(zip(index_vals, ticker_labels)):
        offset = 0.005 if idx_val >= 0 else -0.005
        ha = "left" if idx_val >= 0 else "right"
        ax.text(
            idx_val + offset, i,
            f"{idx_val:+.3f}",
            va="center", ha=ha, fontsize=8, fontweight="bold",
            color=_INDEX_COLOR,
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(ticker_labels, fontsize=10, fontweight="bold")
    ax.axvline(0, color=_GRAY, linewidth=0.8, linestyle="--")

    ax.set_title(
        f"Universe Sentiment Summary — {as_of_date}",
        fontsize=13, fontweight="bold", pad=12, loc="left",
    )
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%+.2f"))
    ax.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.3)
    ax.spines["bottom"].set_alpha(0.3)

    ax.legend(
        loc="lower right", frameon=False, fontsize=8,
        ncol=2,
    )

    fig.tight_layout()

    out_path = output_dir / f"universe_summary_{as_of_date}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return str(out_path)
