"""Load Palworld setting descriptions from the project's metadata file."""

import json
import os
import sys


def _metadata_path():
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "metadata.json")


CACHE_PATH = _metadata_path()
SETTING_METADATA = {}

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
