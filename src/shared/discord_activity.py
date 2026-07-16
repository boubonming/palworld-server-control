"""Formatting and normalization helpers for Discord activity messages."""


def channel_context(channel, author=None):
    guild = getattr(channel, "guild", None)
    guild_name = getattr(guild, "name", "Direct message")
    channel_name = getattr(channel, "name", str(getattr(channel, "id", channel)))
    if author is None:
        return f"{guild_name} / #{channel_name}"
    author_name = getattr(author, "display_name", str(author))
    return f"{guild_name} / #{channel_name} / {author_name}"


def command_activity(channel, author, command, result):
    return f"#{channel_context(channel, author)} · {command} · {result}"


def bot_reply_activity(channel, reply):
    return f"#{channel_context(channel)} / Palworld Bot · Reply: {reply}"


def configured_channel_ids(values):
    return {
        channel_id
        for value in values
        if (channel_id := normalize_channel_id(value)) is not None
    }


def normalize_channel_id(value):
    text = str(value).strip()
    return int(text) if text.isdigit() and int(text) > 0 else None
