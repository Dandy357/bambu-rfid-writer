from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..options import ERASE_SCOPE_NDEF, ERASE_SCOPE_USER
from .widgets import AutoHideScrollbar


class Type2ViewMixin:
    """Build the NFC Type 2 write and erase screen."""

    def _build_type2_write_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)
        ttk.Label(tab, text=self.t("app.ntag_heading"), style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        order_note = self._enable_dynamic_wrap(
            ttk.Label(
                tab,
                text=self.t("app.type2_editor_description"),
                style="Muted.TLabel",
                justify="left",
            )
        )
        order_note.grid(row=1, column=0, sticky="ew", pady=(4, 9))

        editor = ttk.Frame(tab, style="Card.TFrame", padding=1)
        editor.grid(row=2, column=0, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(0, weight=1)
        self.ntag_canvas = tk.Canvas(editor, highlightthickness=0, borderwidth=0)
        self.theme.configure_canvas(self.ntag_canvas, surface=True)
        self.ntag_canvas.grid(row=0, column=0, sticky="nsew")
        scroll = AutoHideScrollbar(
            editor, orient="vertical", command=self.ntag_canvas.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.ntag_canvas.configure(yscrollcommand=scroll.set)
        self.ntag_fields_frame = ttk.Frame(self.ntag_canvas, style="Surface.TFrame", padding=12)
        self.ntag_window = self.ntag_canvas.create_window(
            (0, 0), window=self.ntag_fields_frame, anchor="nw"
        )
        self.ntag_fields_frame.bind("<Configure>", self._sync_type2_scrollregion)
        self.ntag_canvas.bind("<Configure>", self._sync_type2_canvas_width)
        self._render_type2_fields()

        preview = ttk.Frame(tab)
        preview.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        preview.columnconfigure(4, weight=1)
        ttk.Button(
            preview,
            text=self.t("app.add_text_field"),
            image=self.theme.icon("plus"),
            compound="left",
            command=lambda: self._add_custom_field("text"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            preview,
            text=self.t("app.add_url_field"),
            image=self.theme.icon("plus"),
            compound="left",
            command=lambda: self._add_custom_field("uri"),
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(
            preview,
            text=self.t("app.preview_ndef"),
            image=self.theme.icon("diagnostic"),
            compound="left",
            command=self._preview_ndef,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.ndef_read_button = ttk.Button(
            preview,
            text=self.t("app.read_ndef"),
            image=self.theme.icon("nfc"),
            compound="left",
            command=self._start_ndef_read,
        )
        self.ndef_read_button.grid(row=0, column=3, sticky="w", padx=(8, 0))
        ndef_status = self._enable_dynamic_wrap(
            ttk.Label(
                preview,
                textvariable=self.ndef_status_var,
                style="Muted.TLabel",
                justify="left",
            )
        )
        ndef_status.grid(row=0, column=4, sticky="ew", padx=(12, 0))

        ntag_process = self._enable_dynamic_wrap(
            ttk.Label(
                tab,
                text=self.t("app.ntag_process"),
                style="Muted.TLabel",
                justify="left",
            )
        )
        ntag_process.grid(row=4, column=0, sticky="ew", pady=(14, 12))

        actions = ttk.Frame(tab)
        actions.grid(row=5, column=0, sticky="ew")
        actions.columnconfigure(3, weight=1)
        self.ntag_write_button = ttk.Button(
            actions,
            text=self.t("app.write_ntag"),
            image=self.theme.icon("write", inverse=True),
            compound="left",
            style="Type2Accent.TButton",
            command=self._start_type2_write,
            cursor="hand2",
        )
        self.ntag_write_button.grid(row=0, column=0, sticky="w")
        self.ntag_check_button = ttk.Button(
            actions,
            text=self.t("app.check_ndef"),
            image=self.theme.icon("diagnostic"),
            compound="left",
            command=lambda: self._start_diagnostic("type2"),
        )
        self.ntag_check_button.grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Checkbutton(
            actions,
            text=self.t("app.verify_after_write"),
            variable=self.ntag_verify_var,
            command=self._sync_type2_quick_verify,
        ).grid(row=0, column=2, sticky="w", padx=(16, 0))

        erase_actions = ttk.Frame(actions)
        erase_actions.grid(row=0, column=3, sticky="e")
        erase_actions.columnconfigure(0, minsize=210)
        self.ntag_erase_button = ttk.Button(
            erase_actions,
            text=self.t("app.erase_ntag"),
            image=self.theme.icon("erase"),
            compound="left",
            style="WarningOutline.TButton",
            width=28,
            command=lambda: self._start_type2_erase(ERASE_SCOPE_NDEF),
            cursor="hand2",
        )
        self.ntag_erase_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.ntag_full_erase_button = ttk.Button(
            erase_actions,
            text=self.t("app.zero_user_area"),
            image=self.theme.icon("erase", inverse=True),
            compound="left",
            style="Danger.TButton",
            width=15,
            command=lambda: self._start_type2_erase(ERASE_SCOPE_USER),
            cursor="hand2",
        )
        self.ntag_full_erase_button.grid(row=0, column=1)
