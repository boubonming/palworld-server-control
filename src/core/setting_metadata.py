"""Load Palworld setting descriptions from the project's metadata file."""

import json
import os
import re
import sys


def _metadata_path():
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "metadata.json")


CACHE_PATH = _metadata_path()
SETTING_METADATA = {}

# These capacity settings cannot usefully be negative or unlimited. Palworld
# documents their upper bounds but not a lower bound, so the editor uses the
# user-safe minimum of one while preserving documented zero rules elsewhere.
EDITOR_NUMERIC_MINIMUMS = {
    "BaseCampMaxNumInGuild": 1.0,
    "BaseCampWorkerMaxNum": 1.0,
}


def _technology_ids_path():
    return os.path.join(os.path.dirname(CACHE_PATH), "technology_ids.json")

try:
    with open(CACHE_PATH, "r", encoding="utf-8") as cache_file:
        cached = json.load(cache_file)
    for key, value in cached.items():
        description = value.get("description") if isinstance(value, dict) else value
        if description:
            SETTING_METADATA[key] = description
except (OSError, ValueError, TypeError):
    pass


def update_cached_metadata(metadata):
    for key, value in metadata.items():
        description = value.get("description") if isinstance(value, dict) else value
        if description:
            SETTING_METADATA[key] = description
    with open(CACHE_PATH, "w", encoding="utf-8") as cache_file:
        json.dump(metadata, cache_file, indent=2, ensure_ascii=False)


def get_setting_tooltip(key):
    return SETTING_METADATA.get(
        key,
        "No description is available for this Palworld setting.",
    )


def get_setting_numeric_bounds(key):
    """Return numeric limits explicitly stated in a setting description."""
    description = SETTING_METADATA.get(key, "")

    def find_limit(pattern):
        match = re.search(pattern, description, flags=re.IGNORECASE)
        return float(match.group(1).replace(",", "")) if match else None

    minimum = find_limit(r"\bmin(?:imum)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)")
    maximum = find_limit(r"\bmax(?:imum)?\s*[:=]?\s*(-?\d+(?:\.\d+)?)")
    if minimum is None:
        minimum = EDITOR_NUMERIC_MINIMUMS.get(key)
    return minimum, maximum


def get_setting_numeric_hint(key):
    """Summarize documented numeric rules for display beside the input."""
    description = SETTING_METADATA.get(key, "")
    minimum, maximum = get_setting_numeric_bounds(key)
    parts = []

    if minimum is not None and maximum is not None:
        parts.append(f"Allowed range: {minimum:g}–{maximum:g}")
    elif minimum is not None:
        parts.append(f"Minimum: {minimum:g}")
    elif maximum is not None:
        parts.append(f"Maximum: {maximum:g}")

    if re.search(r"\b0\s*=\s*unlimited\b", description, flags=re.IGNORECASE):
        parts.append("0 = unlimited")

    unit_match = re.search(
        r"\((seconds|minutes|hours|cm)\)",
        description,
        flags=re.IGNORECASE,
    )
    if unit_match:
        parts.append(f"Unit: {unit_match.group(1).lower()}")

    default_match = re.search(
        r"\bDefault:\s*(-?\d+(?:\.\d+)?)",
        description,
        flags=re.IGNORECASE,
    )
    if default_match:
        parts.append(f"Default: {default_match.group(1)}")

    ignored_match = re.search(
        r"\bIgnored if\s+([^.]+)",
        description,
        flags=re.IGNORECASE,
    )
    if ignored_match:
        parts.append(f"Ignored if {ignored_match.group(1).strip()}")

    note_match = re.search(r"\bNote:\s*([^.]+)", description, flags=re.IGNORECASE)
    if note_match:
        parts.append(note_match.group(1).strip())

    for warning in (
        "Increasing this value raises processing load",
        "Impacts performance",
    ):
        if warning.lower() in description.lower():
            parts.append(warning)

    return " • ".join(parts)


def get_technology_options():
    try:
        with open(_technology_ids_path(), "r", encoding="utf-8") as technology_file:
            technologies = json.load(technology_file)
        return [(item["name"], item["id"]) for item in technologies]
    except (OSError, ValueError, TypeError, KeyError):
        return []
