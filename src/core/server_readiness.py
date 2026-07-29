"""Determine when a running Palworld process is ready for players."""

import time

from core import api_client, config_manager
from shared.status import ServerState, ServerStatus


def get_status():
    """Return readiness, not merely whether the server process exists."""
    backend = config_manager.get_server_backend()
    if not backend.is_running():
        return ServerStatus(ServerState.STOPPED)

    health_status = None
    health_reader = getattr(backend, "health_status", None)
    if health_reader is not None:
        try:
            health_status = health_reader()
        except Exception:
            health_status = None

    if health_status == "healthy":
        return ServerStatus(ServerState.RUNNING)
    if health_status == "unhealthy":
        return ServerStatus(
            ServerState.STARTING,
            "Starting (Docker health: unhealthy)",
        )
    if health_status == "starting":
        return ServerStatus(ServerState.STARTING)

    try:
        api_client.call_palworld_api("players", method="GET", timeout=2)
    except Exception:
        return ServerStatus(ServerState.STARTING)
    return ServerStatus(ServerState.RUNNING)


def wait_until_ready(
    timeout=600,
    poll_interval=2,
    status_getter=None,
    on_status=None,
    stop_event=None,
):
    """Poll Docker health or the fallback API until Palworld is ready."""
    getter = status_getter or get_status
    deadline = time.monotonic() + timeout
    saw_active_state = False
    last_status = None
    while True:
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Server startup monitoring was cancelled.")
        status = getter()
        last_status = status
        if on_status is not None:
            on_status(status)
        if status.state is ServerState.RUNNING:
            return status
        if status.state is ServerState.STARTING:
            saw_active_state = True
        elif status.state is ServerState.STOPPED and saw_active_state:
            raise RuntimeError(
                "The server container stopped before becoming healthy."
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            detail = last_status.display if last_status is not None else "unknown"
            raise TimeoutError(
                f"Server did not become healthy within {int(timeout)} seconds "
                f"(last status: {detail})."
            )
        wait_seconds = min(poll_interval, remaining)
        if stop_event is not None:
            if stop_event.wait(wait_seconds):
                raise RuntimeError("Server startup monitoring was cancelled.")
        elif wait_seconds:
            time.sleep(wait_seconds)
