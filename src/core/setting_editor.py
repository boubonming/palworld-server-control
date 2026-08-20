"""Toolkit-neutral descriptions for Palworld setting editors."""

import csv
import io
import re

from core.setting_metadata import (
    get_setting_numeric_bounds,
    get_setting_numeric_hint,
    get_technology_options,
)


SETTING_CHOICES = {
    "DeathPenalty": [
        ("No drops", "None"),
        ("Drop items except equipment", "Item"),
        ("Drop items and equipment", "ItemAndEquipment"),
        ("Drop items, equipment, and team Pals", "All"),
    ],
    "RandomizerType": [
        ("No randomization", "None"),
        ("Randomize per region", "Region"),
        ("Fully randomized", "All"),
    ],
    "LogFormatType": [("Text", "Text"), ("JSON", "Json")],
}

MULTI_SELECT_CHOICES = {
    "CrossplayPlatforms": (
        [(platform, platform) for platform in ("Steam", "Xbox", "PS5", "Mac")],
        False,
    ),
}

DISPLAY_NAME_REPLACEMENTS = {
    "Hp": "HP",
    "Pv P": "PvP",
    "U Id": "UID",
}


def setting_display_name(key):
    if key.startswith("b") and len(key) > 1 and key[1].isupper():
        key = key[1:]
    key = key.replace("_", " ")
    key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", key)
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    for source, replacement in DISPLAY_NAME_REPLACEMENTS.items():
        key = key.replace(source, replacement)
    return key


def parse_multi_values(value):
    value = str(value).strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    if not value.strip():
        return []
    try:
        return [
            item.strip().strip('"')
            for item in next(csv.reader(io.StringIO(value), skipinitialspace=True))
            if item.strip().strip('"')
        ]
    except (csv.Error, StopIteration):
        return [item.strip().strip('"') for item in value.split(",") if item.strip()]


def serialize_multi_values(values, quote_values=False):
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if quote_values:
        contents = ",".join(
            f'"{value.replace(chr(34), chr(92) + chr(34))}"'
            for value in cleaned
        )
    else:
        contents = ",".join(cleaned)
    return f"({contents})"


def describe_setting(key, value):
    """Describe the appropriate editor without importing a UI toolkit."""
    value = str(value)
    lowered = value.lower()
    description = {
        "key": key,
        "value": value,
        "kind": "text",
        "secret": "password" in key.lower(),
    }
    if lowered in {"true", "false"}:
        description.update(kind="boolean", checked=lowered == "true")
        return description

    if key in SETTING_CHOICES:
        choices = list(SETTING_CHOICES[key])
        if value not in {choice_value for _label, choice_value in choices}:
            choices.append((value, value))
        description.update(kind="choice", choices=choices)
        return description

    if key == "DenyTechnologyList":
        options, quote_values = get_technology_options(), True
    elif key in MULTI_SELECT_CHOICES:
        options, quote_values = MULTI_SELECT_CHOICES[key]
    else:
        options = None
        quote_values = False
    if options is not None:
        selected = parse_multi_values(value)
        known = {option_value for _label, option_value in options}
        options = list(options) + [
            (unknown, unknown) for unknown in selected if unknown not in known
        ]
        description.update(
            kind="multi",
            choices=options,
            selected=selected,
            quote_values=quote_values,
        )
        return description

    if re.fullmatch(r"-?\d+", value):
        minimum, maximum = get_setting_numeric_bounds(key)
        description.update(
            kind="integer",
            minimum=minimum,
            maximum=maximum,
            slider=minimum is not None and maximum is not None,
            hint=get_setting_numeric_hint(key),
        )
    elif re.fullmatch(r"-?\d+\.\d+", value):
        minimum, maximum = get_setting_numeric_bounds(key)
        description.update(
            kind="decimal",
            minimum=minimum,
            maximum=maximum,
            slider=False,
            hint=get_setting_numeric_hint(key),
        )
    return description
