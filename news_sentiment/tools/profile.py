"""Parse company profiles from research agent initiation reports."""

import glob
import json
import re
from pathlib import Path

import yaml

# Base data directory — resolve relative to this file's location
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_company_profile(ticker: str, data_dir: Path | None = None) -> dict | None:
    """Load and parse a company profile from the most recent initiation .md file.

    Args:
        ticker: Uppercase stock ticker (e.g. "TSLA").
        data_dir: Override for the data directory (useful for testing).

    Returns:
        Structured profile dict, or None if no profile file exists.
    """
    data_dir = Path(data_dir) if data_dir else _DATA_DIR

    # 1. Find the most recent initiation file for this ticker
    md_path = _find_latest_profile(ticker, data_dir / "profiles")
    if md_path is None:
        return None

    # 2. Extract and parse the YAML tag block
    raw_yaml = _extract_yaml_block(md_path.read_text())
    if raw_yaml is None:
        return None

    level_1, level_2_clusters = _parse_tag_yaml(raw_yaml)

    # 3. Look up concept URI
    concept_uri = _load_concept_uri(ticker, data_dir / "concept_map.json")

    return {
        "ticker": ticker,
        "concept_uri": concept_uri,
        "level_1": level_1,
        "level_2_clusters": level_2_clusters,
    }


def _find_latest_profile(ticker: str, profiles_dir: Path) -> Path | None:
    """Return the path to the most recent initiation .md for *ticker*, or None."""
    pattern = str(profiles_dir / f"{ticker}_initiation_*.md")
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    # Filenames contain ISO dates — last in sorted order is the most recent
    return Path(matches[-1])


def _extract_yaml_block(text: str) -> str | None:
    """Pull the fenced ```yaml block from under the ## Tags heading."""
    # Find the ## Tags section, then grab the first ```yaml ... ``` block after it
    tags_match = re.search(r"^## Tags\s*$", text, re.MULTILINE)
    if not tags_match:
        return None

    remainder = text[tags_match.end():]
    yaml_match = re.search(r"```yaml\s*\n(.*?)```", remainder, re.DOTALL)
    if not yaml_match:
        return None

    return yaml_match.group(1)


def _parse_tag_yaml(raw: str) -> tuple[dict, list[dict]]:
    """Parse the YAML tag block, splitting at the # Level 2 comment.

    The block contains two logical sections separated by a ``# Level 2``
    comment line.  We split there and parse each half independently so the
    ``# Level 1`` / ``# Level 2`` comments (which aren't valid YAML keys)
    don't interfere with the parser.
    """
    # Split at the "# Level 2" comment line
    parts = re.split(r"^# Level 2\s*$", raw, maxsplit=1, flags=re.MULTILINE)

    # --- Level 1 ---
    l1_raw = parts[0]
    # Strip the "# Level 1" comment so only clean YAML remains
    l1_raw = re.sub(r"^# Level 1\s*$", "", l1_raw, flags=re.MULTILINE)
    l1_data = yaml.safe_load(l1_raw) or {}
    tags = l1_data.get("Tags", {})

    level_1 = {
        "sectors": tags.get("Sectors", []),
        "industries": tags.get("Industries", []),
        "trends": tags.get("Trends", []),
        "themes": tags.get("Themes", []),
    }

    # --- Level 2 ---
    level_2_clusters: list[dict] = []
    if len(parts) > 1:
        l2_data = yaml.safe_load(parts[1]) or {}
        for cluster in l2_data.get("Clusters", []):
            level_2_clusters.append({
                "name": cluster["name"],
                "relevance": cluster["relevance"],
                "member_tags": cluster["member_tags"],
            })

    return level_1, level_2_clusters


def _load_concept_uri(ticker: str, concept_map_path: Path) -> str | None:
    """Read concept_map.json and return the URI for *ticker*, or None."""
    if not concept_map_path.exists():
        return None
    with open(concept_map_path) as f:
        mapping = json.load(f)
    return mapping.get(ticker)
