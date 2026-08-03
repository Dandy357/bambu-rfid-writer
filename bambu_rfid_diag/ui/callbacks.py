from __future__ import annotations

import itertools
import tkinter as tk
from collections.abc import Callable
from typing import Any


class CallbackRegistry:
    """Own and cancel deferred Tk callbacks across UI rebuilds and shutdown."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._callbacks: dict[str, tuple[tk.Misc, str]] = {}
        self._keys: dict[tuple[int, str], str] = {}
        self._counter = itertools.count()

    def schedule(
        self,
        widget: tk.Misc,
        delay_ms: int,
        callback: Callable[[], Any],
        *,
        key: str | None = None,
    ) -> str:
        """Schedule a callback, optionally replacing an earlier callback with the same key."""

        logical_key = (id(widget), key) if key is not None else None
        if logical_key is not None:
            existing = self._keys.get(logical_key)
            if existing is not None:
                self.cancel(existing)

        token = f"callback-{next(self._counter)}"

        def invoke() -> None:
            self._discard(token)
            try:
                if widget.winfo_exists():
                    callback()
            except tk.TclError:
                return

        after_id = widget.after(max(0, int(delay_ms)), invoke)
        self._callbacks[token] = (widget, after_id)
        if logical_key is not None:
            self._keys[logical_key] = token
        return token

    def idle(
        self,
        widget: tk.Misc,
        callback: Callable[[], Any],
        *,
        key: str | None = None,
    ) -> str:
        """Schedule a callback after Tk becomes idle."""

        logical_key = (id(widget), key) if key is not None else None
        if logical_key is not None:
            existing = self._keys.get(logical_key)
            if existing is not None:
                self.cancel(existing)

        token = f"callback-{next(self._counter)}"

        def invoke() -> None:
            self._discard(token)
            try:
                if widget.winfo_exists():
                    callback()
            except tk.TclError:
                return

        after_id = widget.after_idle(invoke)
        self._callbacks[token] = (widget, after_id)
        if logical_key is not None:
            self._keys[logical_key] = token
        return token

    def cancel(self, token: str) -> None:
        """Cancel one registered callback if it is still pending."""

        entry = self._callbacks.pop(token, None)
        if entry is None:
            return
        widget, after_id = entry
        self._remove_key(token)
        try:
            widget.after_cancel(after_id)
        except tk.TclError:
            return

    def cancel_all(self) -> None:
        """Cancel every pending callback registered for the application."""

        for token in list(self._callbacks):
            self.cancel(token)
        self._keys.clear()

    def _discard(self, token: str) -> None:
        self._callbacks.pop(token, None)
        self._remove_key(token)

    def _remove_key(self, token: str) -> None:
        for logical_key, value in list(self._keys.items()):
            if value == token:
                self._keys.pop(logical_key, None)
