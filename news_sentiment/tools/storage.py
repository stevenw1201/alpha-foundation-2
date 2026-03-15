"""Persist scored articles and macro events to daily JSON files.

Both functions are idempotent on article/event ID — re-scoring the same
article overwrites the previous entry rather than creating a duplicate.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def store_scored_articles(
    ticker: str,
    articles: list[dict],
    *,
    data_dir: Path | None = None,
) -> int:
    """Append scored company-specific articles to daily JSON files.

    Articles are grouped by publication date and written to
    ``data/articles/{TICKER}/{YYYY-MM-DD}.json``.  Idempotent on ``id`` —
    if an article with the same id already exists in the file it is replaced.

    Args:
        ticker: Uppercase stock ticker.
        articles: List of scored article dicts (must contain ``id`` and
            ``published_at``).
        data_dir: Override for the data directory.

    Returns:
        Number of articles written (new + updated).
    """
    data_dir = Path(data_dir) if data_dir else _DATA_DIR
    articles_dir = data_dir / "articles" / ticker
    articles_dir.mkdir(parents=True, exist_ok=True)

    # Group articles by publication date
    by_date: dict[str, list[dict]] = {}
    for art in articles:
        pub_date = _extract_date(art["published_at"])
        by_date.setdefault(pub_date, []).append(art)

    written = 0
    for pub_date, new_articles in by_date.items():
        path = articles_dir / f"{pub_date}.json"
        existing = _read_json_list(path)

        # Build lookup of existing articles by id for idempotent upsert
        by_id = {a["id"]: a for a in existing}
        for art in new_articles:
            by_id[art["id"]] = art
            written += 1

        _write_json_list(path, list(by_id.values()))

    return written


def store_macro_events(
    events: list[dict],
    *,
    data_dir: Path | None = None,
) -> int:
    """Append macro event scorings to daily JSON files.

    Events are grouped by publication date and written to
    ``data/macro/{YYYY-MM-DD}.json``.  Idempotent on ``id``.

    Args:
        events: List of macro event dicts (must contain ``id`` and
            ``published_at``).
        data_dir: Override for the data directory.

    Returns:
        Number of events written (new + updated).
    """
    data_dir = Path(data_dir) if data_dir else _DATA_DIR
    macro_dir = data_dir / "macro"
    macro_dir.mkdir(parents=True, exist_ok=True)

    by_date: dict[str, list[dict]] = {}
    for evt in events:
        pub_date = _extract_date(evt["published_at"])
        by_date.setdefault(pub_date, []).append(evt)

    written = 0
    for pub_date, new_events in by_date.items():
        path = macro_dir / f"{pub_date}.json"
        existing = _read_json_list(path)

        by_id = {e["id"]: e for e in existing}
        for evt in new_events:
            by_id[evt["id"]] = evt
            written += 1

        _write_json_list(path, list(by_id.values()))

    return written


def save_index_result(
    index_result: dict,
    *,
    data_dir: Path | None = None,
) -> Path:
    """Append an index result to the ticker's index history file.

    Written to ``data/index/{TICKER}_index.json``.  Idempotent on
    ``as_of_date`` — re-running for the same date overwrites.

    Returns:
        Path to the index history file.
    """
    data_dir = Path(data_dir) if data_dir else _DATA_DIR
    index_dir = data_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    ticker = index_result["ticker"]
    path = index_dir / f"{ticker}_index.json"
    existing = _read_json_list(path)

    # Upsert by as_of_date
    by_date = {r["as_of_date"]: r for r in existing}
    by_date[index_result["as_of_date"]] = index_result
    # Sort chronologically
    sorted_history = sorted(by_date.values(), key=lambda r: r["as_of_date"])

    _write_json_list(path, sorted_history)
    return path


def load_index_history(
    ticker: str,
    *,
    data_dir: Path | None = None,
) -> list[dict]:
    """Load the full index history for a ticker.

    Returns:
        List of index result dicts sorted by date, or [].
    """
    data_dir = Path(data_dir) if data_dir else _DATA_DIR
    path = data_dir / "index" / f"{ticker}_index.json"
    return _read_json_list(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_date(published_at: str) -> str:
    """Return the YYYY-MM-DD portion of a datetime string."""
    return datetime.fromisoformat(published_at.replace("Z", "+00:00")).strftime("%Y-%m-%d")


def _read_json_list(path: Path) -> list[dict]:
    """Read a JSON file containing a list, or return [] if it doesn't exist."""
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def _write_json_list(path: Path, data: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
