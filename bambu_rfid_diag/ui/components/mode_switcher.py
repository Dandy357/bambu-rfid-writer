from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

from ..constants import MODE_CUID, MODE_SETTINGS, MODE_TYPE2
from ..theme import ThemeManager


class ModeSwitcher(ttk.Frame):
    """Compact primary navigation for CUID, NFC Type 2, and Settings."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        theme: ThemeManager,
        translate: Callable[[str], str],
        command: Callable[[str], None],
        selected: str = MODE_CUID,
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self.translate = translate
        self.command = command
        self.selected = selected

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1, uniform="protocol")
        self.columnconfigure(2, weight=1, uniform="protocol")

        self.settings_button = ttk.Button(
            self,
            text="",
            image=theme.icon("settings", size=32),
            compound="top",
            style="ModeSettingsIdle.TButton",
            command=lambda: self.select(MODE_SETTINGS),
            cursor="hand2",
            width=3,
        )
        self.settings_button.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        self.cuid_button = ttk.Button(
            self,
            text=translate("app.tab_bambu"),
            image=theme.icon("chip"),
            compound="left",
            command=lambda: self.select(MODE_CUID),
            cursor="hand2",
        )
        self.cuid_button.grid(row=0, column=1, sticky="ew", padx=(0, 4))

        self.type2_button = ttk.Button(
            self,
            text=translate("app.tab_ntag"),
            image=theme.icon("nfc"),
            compound="left",
            command=lambda: self.select(MODE_TYPE2),
            cursor="hand2",
        )
        self.type2_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self._apply_selection()

    @property
    def buttons(self) -> tuple[ttk.Button, ttk.Button, ttk.Button]:
        return self.settings_button, self.cuid_button, self.type2_button

    def select(self, mode: str, *, notify: bool = True) -> None:
        if mode not in {MODE_CUID, MODE_TYPE2, MODE_SETTINGS}:
            return
        self.selected = mode
        self._apply_selection()
        if notify:
            self.command(mode)

    def _apply_selection(self) -> None:
        settings_selected = self.selected == MODE_SETTINGS
        self.settings_button.configure(
            style=(
                "ModeSettingsSelected.TButton"
                if settings_selected
                else "ModeSettingsIdle.TButton"
            ),
            image=self.theme.icon("settings", size=32, inverse=settings_selected),
        )

        cuid_selected = self.selected == MODE_CUID
        self.cuid_button.configure(
            style="ModeCuid.TButton" if cuid_selected else "ModeIdle.TButton",
            image=self.theme.icon("chip", inverse=cuid_selected),
        )

        type2_selected = self.selected == MODE_TYPE2
        self.type2_button.configure(
            style="ModeType2.TButton" if type2_selected else "ModeIdle.TButton",
            image=self.theme.icon("nfc", inverse=type2_selected),
        )
