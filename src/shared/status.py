"""Shared server state and status presentation rules."""

from dataclasses import dataclass
from enum import Enum


class ServerState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ServerStatus:
    state: ServerState
    label: str | None = None

    @property
    def display(self):
        return self.label or self.state.value.capitalize()


def is_active_status(status):
    if isinstance(status, ServerStatus):
        return status.state is ServerState.RUNNING
    lowered = str(status).lower()
    return lowered.startswith("running") or lowered.startswith("online")


def status_color(status):
    if isinstance(status, ServerStatus):
        if status.state is ServerState.RUNNING:
            return "#63d471"
        if status.state is ServerState.STOPPED:
            return "#ff6b6b"
        return "#f2c94c"
    lowered = str(status).lower()
    if is_active_status(lowered):
        return "#63d471"
    if lowered.startswith("stopped") or lowered.startswith("off") or "offline" in lowered:
        return "#ff6b6b"
    return "#f2c94c"


def status_stylesheet(status):
    return f"color: {status_color(status)};"
