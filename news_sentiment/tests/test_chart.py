"""Tests for tools/chart.py — validates chart generation with synthetic data."""

import json
from pathlib import Path

import pytest

from news_sentiment.tools.chart import generate_index_chart, generate_universe_summary
from news_sentiment.tools.storage import save_index_result


def _make_index_result(ticker, as_of_date, index_value, company, macro):
    return {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "index_value": index_value,
        "company_component": company,
        "macro_component": macro,
        "article_count": 5,
        "macro_event_count": 2,
        "top_company_contributors": [
            {"headline": "Big positive news", "contribution": 0.12, "days_old": 0},
            {"headline": "Minor update", "contribution": 0.03, "days_old": 1},
        ],
        "top_macro_contributors": [
            {"headline": "Fed decision", "contribution": -0.08, "days_old": 0},
        ],
        "index_history": [],
    }


@pytest.fixture()
def data_with_history(tmp_path):
    """Create a tmp data dir with 7 days of TSLA index history."""
    data_dir = tmp_path / "data"
    (data_dir / "index").mkdir(parents=True)

    # 7 days of data with varying values
    days = [
        ("2026-03-07", +0.05, +0.10, -0.05),
        ("2026-03-08", -0.02, +0.03, -0.05),
        ("2026-03-09", +0.12, +0.15, -0.03),
        ("2026-03-10", -0.15, -0.05, -0.10),
        ("2026-03-11", -0.08, +0.02, -0.10),
        ("2026-03-12", +0.20, +0.25, -0.05),
        ("2026-03-13", +0.07, +0.15, -0.08),
    ]
    for d, idx, co, ma in days:
        result = _make_index_result("TSLA", d, idx, co, ma)
        save_index_result(result, data_dir=data_dir)

    return data_dir


# ---------------------------------------------------------------------------
# generate_index_chart
# ---------------------------------------------------------------------------

class TestGenerateIndexChart:
    def test_creates_png(self, data_with_history, tmp_path):
        out_dir = tmp_path / "output"
        path = generate_index_chart(
            "TSLA", days=7,
            data_dir=data_with_history, output_dir=out_dir,
        )
        assert path is not None
        assert Path(path).exists()
        assert path.endswith(".png")

    def test_returns_none_for_missing_ticker(self, data_with_history, tmp_path):
        out_dir = tmp_path / "output"
        path = generate_index_chart(
            "ZZZZ", days=7,
            data_dir=data_with_history, output_dir=out_dir,
        )
        assert path is None

    def test_chart_file_has_content(self, data_with_history, tmp_path):
        out_dir = tmp_path / "output"
        path = generate_index_chart(
            "TSLA", days=7,
            data_dir=data_with_history, output_dir=out_dir,
        )
        size = Path(path).stat().st_size
        assert size > 5000  # a real PNG chart should be > 5KB


# ---------------------------------------------------------------------------
# generate_universe_summary
# ---------------------------------------------------------------------------

class TestGenerateUniverseSummary:
    def test_creates_png(self, data_with_history, tmp_path):
        # Add a second ticker
        for d, idx, co, ma in [("2026-03-13", -0.10, -0.03, -0.07)]:
            save_index_result(
                _make_index_result("NVDA", d, idx, co, ma),
                data_dir=data_with_history,
            )
        out_dir = tmp_path / "output"
        path = generate_universe_summary(
            ["TSLA", "NVDA"], "2026-03-13",
            data_dir=data_with_history, output_dir=out_dir,
        )
        assert path is not None
        assert Path(path).exists()
        assert "universe_summary" in path

    def test_returns_none_for_no_data(self, tmp_path):
        data_dir = tmp_path / "data"
        (data_dir / "index").mkdir(parents=True)
        out_dir = tmp_path / "output"
        path = generate_universe_summary(
            ["ZZZZ"], "2026-03-13",
            data_dir=data_dir, output_dir=out_dir,
        )
        assert path is None

    def test_single_ticker_works(self, data_with_history, tmp_path):
        out_dir = tmp_path / "output"
        path = generate_universe_summary(
            ["TSLA"], "2026-03-13",
            data_dir=data_with_history, output_dir=out_dir,
        )
        assert path is not None


# ---------------------------------------------------------------------------
# save_index_result / load_index_history
# ---------------------------------------------------------------------------

class TestIndexPersistence:
    def test_save_and_load(self, tmp_path):
        data_dir = tmp_path / "data"
        result = _make_index_result("TSLA", "2026-03-13", 0.15, 0.20, -0.05)
        save_index_result(result, data_dir=data_dir)

        from news_sentiment.tools.storage import load_index_history
        history = load_index_history("TSLA", data_dir=data_dir)
        assert len(history) == 1
        assert history[0]["as_of_date"] == "2026-03-13"
        assert history[0]["index_value"] == 0.15

    def test_idempotent_on_date(self, tmp_path):
        data_dir = tmp_path / "data"
        save_index_result(
            _make_index_result("TSLA", "2026-03-13", 0.10, 0.15, -0.05),
            data_dir=data_dir,
        )
        save_index_result(
            _make_index_result("TSLA", "2026-03-13", 0.20, 0.25, -0.05),
            data_dir=data_dir,
        )

        from news_sentiment.tools.storage import load_index_history
        history = load_index_history("TSLA", data_dir=data_dir)
        assert len(history) == 1
        assert history[0]["index_value"] == 0.20  # overwritten

    def test_sorted_chronologically(self, tmp_path):
        data_dir = tmp_path / "data"
        # Insert out of order
        save_index_result(
            _make_index_result("TSLA", "2026-03-13", 0.10, 0.15, -0.05),
            data_dir=data_dir,
        )
        save_index_result(
            _make_index_result("TSLA", "2026-03-11", -0.05, 0.00, -0.05),
            data_dir=data_dir,
        )
        save_index_result(
            _make_index_result("TSLA", "2026-03-12", 0.02, 0.07, -0.05),
            data_dir=data_dir,
        )

        from news_sentiment.tools.storage import load_index_history
        history = load_index_history("TSLA", data_dir=data_dir)
        dates = [r["as_of_date"] for r in history]
        assert dates == ["2026-03-11", "2026-03-12", "2026-03-13"]
