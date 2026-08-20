"""Parsing helpers for Palworld's OptionSettings INI value."""

import re


def parse_option_settings(raw_options):
    """Split OptionSettings while preserving commas in quotes and nesting."""
    parts = []
    start = 0
    quoted = False
    depth = 0
    for index, character in enumerate(raw_options):
        if character == '"':
            quoted = not quoted
        elif not quoted and character == "(":
            depth += 1
        elif not quoted and character == ")":
            depth -= 1
        elif not quoted and depth == 0 and character == ",":
            parts.append(raw_options[start:index])
            start = index + 1
    parts.append(raw_options[start:])
    return [
        (key.strip(), value.strip())
        for part in parts
        if "=" in part
        for key, value in [part.split("=", 1)]
    ]


def extract_option_settings(contents):
    match = re.search(r"(?m)^OptionSettings=\((.*)\)\s*$", contents)
    if not match:
        return {}
    return {
        key: value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value
        for key, value in parse_option_settings(match.group(1))
    }
