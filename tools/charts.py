"""
Chart Generation Tool
Generates publication-quality financial charts for equity research reports.

Usage:
    python tools/charts.py --type line \
        --data '{"labels":["2020","2021","2022","2023","2024"],"series":[{"name":"Revenue ($B)","values":[28.0,33.7,39.4,44.2,51.3]}]}' \
        --title "Revenue Trend" \
        --output output/charts/AAPL_revenue.png

    python tools/charts.py --type bar \
        --data '{"labels":["Q1","Q2","Q3","Q4"],"series":[{"name":"Gross Margin","values":[45.2,44.8,46.1,45.9]}]}' \
        --title "Quarterly Gross Margin %" \
        --output output/charts/AAPL_margins.png

    python tools/charts.py --type stacked_bar \
        --data '{"labels":["2020","2021","2022","2023","2024"],"series":[{"name":"Americas","values":[46,51,59,63,67]},{"name":"EMEA","values":[22,25,28,30,32]},{"name":"APAC","values":[10,13,15,17,20]}]}' \
        --title "Revenue by Geography ($B)" \
        --output output/charts/AAPL_geo_mix.png

    python tools/charts.py --type dual_axis \
        --data '{"labels":["2020","2021","2022","2023","2024"],"left":{"name":"Revenue ($B)","values":[28,34,39,44,51]},"right":{"name":"Net Margin %","values":[21,26,25,26,27]}}' \
        --title "Revenue vs Net Margin" \
        --output output/charts/AAPL_rev_margin.png

Chart Types: line, bar, stacked_bar, dual_axis, waterfall, pie
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
except ImportError:
    print("ERROR: matplotlib not installed. Run: pip install matplotlib --break-system-packages")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Style Configuration — Institutional research aesthetic
# ---------------------------------------------------------------------------
COLORS = [
    "#1B4F72",  # Deep blue (primary)
    "#2E86C1",  # Medium blue
    "#85C1E9",  # Light blue
    "#1A5276",  # Navy
    "#48C9B0",  # Teal accent
    "#E74C3C",  # Red (for negative/risk)
    "#F39C12",  # Amber (for caution)
    "#27AE60",  # Green (for positive)
]

STYLE_CONFIG = {
    "figure.figsize": (10, 6),
    "figure.dpi": 150,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#CCCCCC",
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": "#E8E8E8",
    "grid.linewidth": 0.5,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "legend.framealpha": 0.9,
}

plt.rcParams.update(STYLE_CONFIG)


def ensure_output_dir(output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Chart Types
# ---------------------------------------------------------------------------

def chart_line(data: dict, title: str, output: str, subtitle: str = ""):
    """Line chart with optional multiple series."""
    fig, ax = plt.subplots()
    labels = data["labels"]
    x = range(len(labels))

    for i, series in enumerate(data["series"]):
        color = COLORS[i % len(COLORS)]
        ax.plot(x, series["values"], marker="o", color=color, linewidth=2,
                markersize=5, label=series["name"], zorder=3)

        # Data labels on last point
        last_val = series["values"][-1]
        ax.annotate(f"{last_val:,.1f}", xy=(len(labels)-1, last_val),
                    xytext=(8, 0), textcoords="offset points",
                    fontsize=8, color=color, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45 if len(labels) > 8 else 0, ha="right")
    ax.set_title(title, pad=15)
    if subtitle:
        ax.text(0.5, 1.02, subtitle, transform=ax.transAxes, ha="center",
                fontsize=9, color="#666666")
    ax.legend(loc="upper left", frameon=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart saved: {output}")


def chart_bar(data: dict, title: str, output: str, subtitle: str = ""):
    """Grouped bar chart."""
    fig, ax = plt.subplots()
    labels = data["labels"]
    n_series = len(data["series"])
    bar_width = 0.7 / n_series
    x = range(len(labels))

    for i, series in enumerate(data["series"]):
        offset = (i - n_series / 2 + 0.5) * bar_width
        positions = [xi + offset for xi in x]
        bars = ax.bar(positions, series["values"], bar_width,
                       color=COLORS[i % len(COLORS)], label=series["name"],
                       edgecolor="white", linewidth=0.5, zorder=3)

        # Value labels on bars
        for bar, val in zip(bars, series["values"]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f"{val:,.1f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45 if len(labels) > 6 else 0, ha="right")
    ax.set_title(title, pad=15)
    if n_series > 1:
        ax.legend(loc="upper left", frameon=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart saved: {output}")


def chart_stacked_bar(data: dict, title: str, output: str, subtitle: str = ""):
    """Stacked bar chart for composition analysis."""
    fig, ax = plt.subplots()
    labels = data["labels"]
    x = range(len(labels))
    bottom = [0] * len(labels)

    for i, series in enumerate(data["series"]):
        ax.bar(x, series["values"], bottom=bottom, color=COLORS[i % len(COLORS)],
               label=series["name"], edgecolor="white", linewidth=0.5, width=0.6, zorder=3)
        bottom = [b + v for b, v in zip(bottom, series["values"])]

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45 if len(labels) > 8 else 0, ha="right")
    ax.set_title(title, pad=15)
    ax.legend(loc="upper left", frameon=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart saved: {output}")


def chart_dual_axis(data: dict, title: str, output: str, subtitle: str = ""):
    """Dual-axis chart (bar + line) for showing two related metrics."""
    fig, ax1 = plt.subplots()
    labels = data["labels"]
    x = range(len(labels))

    left = data["left"]
    right = data["right"]

    # Left axis — bars
    ax1.bar(x, left["values"], color=COLORS[0], alpha=0.8, width=0.6,
            label=left["name"], edgecolor="white", linewidth=0.5, zorder=3)
    ax1.set_ylabel(left["name"], color=COLORS[0])
    ax1.tick_params(axis="y", labelcolor=COLORS[0])

    # Right axis — line
    ax2 = ax1.twinx()
    ax2.plot(x, right["values"], color=COLORS[5], marker="o", linewidth=2,
             markersize=6, label=right["name"], zorder=4)
    ax2.set_ylabel(right["name"], color=COLORS[5])
    ax2.tick_params(axis="y", labelcolor=COLORS[5])

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=45 if len(labels) > 8 else 0, ha="right")
    ax1.set_title(title, pad=15)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", frameon=True)

    ax1.spines["top"].set_visible(False)
    ax2.spines["top"].set_visible(False)

    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart saved: {output}")


def chart_waterfall(data: dict, title: str, output: str, subtitle: str = ""):
    """Waterfall chart for bridge analysis (e.g., EBITDA bridge)."""
    fig, ax = plt.subplots()
    labels = data["labels"]
    values = data["series"][0]["values"]
    n = len(values)

    cumulative = [0] * (n + 1)
    for i in range(n):
        cumulative[i + 1] = cumulative[i] + values[i]

    for i in range(n):
        bottom = min(cumulative[i], cumulative[i + 1])
        height = abs(values[i])
        color = COLORS[7] if values[i] >= 0 else COLORS[5]

        # First and last bars start from 0
        if i == 0 or i == n - 1:
            bottom = 0
            height = cumulative[i + 1] if i == n - 1 else values[i]
            color = COLORS[0]

        ax.bar(i, height, bottom=bottom, color=color, width=0.6,
               edgecolor="white", linewidth=0.5, zorder=3)
        ax.text(i, bottom + height + 0.5, f"{values[i]:+,.1f}" if i not in (0, n-1) else f"{height:,.1f}",
                ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_title(title, pad=15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.axhline(y=0, color="#333333", linewidth=0.8)

    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart saved: {output}")


def chart_pie(data: dict, title: str, output: str, subtitle: str = ""):
    """Pie/donut chart for composition."""
    fig, ax = plt.subplots()
    series = data["series"][0]
    values = series["values"]
    labels = data["labels"]
    colors = COLORS[:len(values)]

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, pctdistance=0.75, wedgeprops={"linewidth": 2, "edgecolor": "white"}
    )

    # Donut style
    centre_circle = plt.Circle((0, 0), 0.50, fc="white")
    ax.add_artist(centre_circle)

    for autotext in autotexts:
        autotext.set_fontsize(9)
        autotext.set_fontweight("bold")

    ax.set_title(title, pad=15)

    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Chart saved: {output}")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
CHART_TYPES = {
    "line": chart_line,
    "bar": chart_bar,
    "stacked_bar": chart_stacked_bar,
    "dual_axis": chart_dual_axis,
    "waterfall": chart_waterfall,
    "pie": chart_pie,
}


def main():
    parser = argparse.ArgumentParser(description="Financial Chart Generator")
    parser.add_argument("--type", required=True, choices=list(CHART_TYPES.keys()),
                        help="Chart type")
    parser.add_argument("--data", required=True,
                        help="JSON string or path to JSON file with chart data")
    parser.add_argument("--title", required=True, help="Chart title")
    parser.add_argument("--subtitle", default="", help="Chart subtitle")
    parser.add_argument("--output", required=True, help="Output file path (PNG)")

    args = parser.parse_args()

    # Parse data
    if args.data.endswith(".json") and Path(args.data).exists():
        data = json.loads(Path(args.data).read_text())
    else:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON data: {e}")
            sys.exit(1)

    ensure_output_dir(args.output)

    chart_fn = CHART_TYPES[args.type]
    chart_fn(data, args.title, args.output, args.subtitle)


if __name__ == "__main__":
    main()
