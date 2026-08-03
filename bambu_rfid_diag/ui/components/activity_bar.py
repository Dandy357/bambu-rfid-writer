from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..constants import MODE_CUID, MODE_TYPE2
from ..theme import ThemeManager


class ActivityBar(ttk.Frame):
    """Animated activity indicator with idle, running, and cancelling states."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        theme: ThemeManager,
        textvariable: tk.StringVar,
    ) -> None:
        super().__init__(parent, style="Card.TFrame", padding=(12, 8))
        self.theme = theme
        self.textvariable = textvariable
        self._state = "idle"
        self._mode = MODE_CUID
        self._phase = 0.0
        self._after_id: str | None = None
        self._resize_after_id: str | None = None

        self.icon_label = ttk.Label(
            self,
            image=theme.muted_icon("ready"),
            style="SurfaceMuted.TLabel",
        )
        self.icon_label.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 9))
        self.canvas = tk.Canvas(
            self,
            height=10,
            width=300,
            highlightthickness=0,
            borderwidth=0,
            background=theme.palette.surface,
        )
        self.canvas.grid(row=0, column=1, sticky="w")
        self.canvas.bind("<Configure>", self._schedule_resize_draw, add="+")
        self.label = ttk.Label(self, textvariable=textvariable, style="SurfaceMuted.TLabel")
        self.label.grid(row=1, column=1, sticky="w", pady=(3, 0))
        self._draw()

    def start(self, mode: str) -> None:
        self._state = "running"
        self._mode = mode if mode in {MODE_CUID, MODE_TYPE2} else MODE_CUID
        self.icon_label.configure(
            image=self.theme.icon("chip" if self._mode == MODE_CUID else "nfc")
        )
        self._schedule()
        self._draw()

    def set_cancelling(self) -> None:
        self._state = "cancelling"
        self.icon_label.configure(image=self.theme.status_icon("warning"))
        self._schedule()
        self._draw()

    def stop(self, *, state: str = "idle") -> None:
        self._state = state
        self._cancel_animation()
        icon_state = "error" if state == "error" else "ok" if state == "success" else "skipped"
        if state == "idle":
            self.icon_label.configure(image=self.theme.muted_icon("ready"))
        else:
            self.icon_label.configure(image=self.theme.status_icon(icon_state))
        self._draw()

    def _schedule(self) -> None:
        if self._after_id is None:
            self._after_id = self.after(35, self._animate)

    def _animate(self) -> None:
        self._after_id = None
        if self._state not in {"running", "cancelling"}:
            return
        self._phase = (self._phase + 0.025) % 1.0
        self._draw()
        self._schedule()

    def _cancel_animation(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _schedule_resize_draw(self, _event: object | None = None) -> None:
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.after(30, self._apply_resize_draw)

    def _apply_resize_draw(self) -> None:
        self._resize_after_id = None
        self._draw()

    def _draw(self, _event: object | None = None) -> None:
        self.canvas.delete("all")
        width = max(24, self.canvas.winfo_width())
        y = 5
        p = self.theme.palette
        self.canvas.create_line(6, y, width - 6, y, fill=p.track, width=7, capstyle="round")
        if self._state in {"running", "cancelling"}:
            if self._state == "cancelling":
                color = p.warning
            else:
                color = p.cuid if self._mode == MODE_CUID else p.type2
            available = width - 12
            segment = max(36, round(available * 0.28))
            start = round((available + segment) * self._phase) - segment + 6
            end = start + segment
            clipped_start = max(6, start)
            clipped_end = min(width - 6, end)
            if clipped_end > clipped_start:
                self.canvas.create_line(
                    clipped_start,
                    y,
                    clipped_end,
                    y,
                    fill=color,
                    width=7,
                    capstyle="round",
                )
        elif self._state == "success":
            self.canvas.create_line(6, y, width - 6, y, fill=p.ok, width=7, capstyle="round")
        elif self._state == "error":
            self.canvas.create_line(6, y, width - 6, y, fill=p.error, width=7, capstyle="round")

    def destroy(self) -> None:
        self._cancel_animation()
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
            self._resize_after_id = None
        super().destroy()
