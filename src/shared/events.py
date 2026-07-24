"""Small toolkit-neutral event helpers shared by desktop and headless runtimes."""

import threading
import traceback


class EventSignal:
    """Provides the connect/emit subset used by the application."""

    def __init__(self):
        self._callbacks = []
        self._lock = threading.Lock()

    def connect(self, callback):
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def emit(self, *args):
        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            try:
                callback(*args)
            except Exception:
                traceback.print_exc()
