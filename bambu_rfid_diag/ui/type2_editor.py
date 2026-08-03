from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..nfc_type2 import Type2Field, build_type2_ndef
from ..type2 import MAX_KNOWN_NDEF_CAPACITY
from .widgets import AutoHideScrollbar


class Type2EditorMixin:
    """Presentation behavior for the ordered NFC Type 2 / NDEF field editor."""

    def _sync_type2_scrollregion(self, _event: object | None = None) -> None:
        self.callbacks.schedule(
            self.ntag_canvas,
            30,
            self._apply_type2_scrollregion,
            key="type2-scrollregion",
        )

    def _apply_type2_scrollregion(self) -> None:
        try:
            self.ntag_canvas.configure(scrollregion=self.ntag_canvas.bbox("all"))
        except tk.TclError:
            return

    def _sync_type2_canvas_width(self, event: tk.Event) -> None:
        self._type2_pending_width = max(1, event.width)
        self.callbacks.schedule(
            self.ntag_canvas,
            20,
            self._apply_type2_canvas_width,
            key="type2-canvas-width",
        )

    def _apply_type2_canvas_width(self) -> None:
        try:
            current = int(float(self.ntag_canvas.itemcget(self.ntag_window, "width") or 0))
            if current != self._type2_pending_width:
                self.ntag_canvas.itemconfigure(
                    self.ntag_window, width=self._type2_pending_width
                )
        except (tk.TclError, TypeError, ValueError):
            return

    def _type2_field_name(self, item: dict[str, object]) -> str:
        label_key = item.get("label_key")
        if label_key:
            return self.t(str(label_key))
        name_var = item.get("name_var")
        return "" if name_var is None else str(name_var.get())

    def _render_type2_fields(self) -> None:
        for child in self.ntag_fields_frame.winfo_children():
            child.destroy()
        frame = self.ntag_fields_frame
        frame.columnconfigure(2, weight=1)
        headings = [
            self.t("app.order"),
            self.t("app.field_name"),
            self.t("app.field_value"),
            self.t("app.write_field_name"),
            self.t("app.field_actions"),
        ]
        for column, heading in enumerate(headings):
            ttk.Label(
                frame,
                text=heading,
                style="Surface.TLabel",
                font=("Segoe UI", 9, "bold"),
            ).grid(row=0, column=column, sticky="w", padx=5, pady=(0, 6))

        if not self.type2_fields:
            ttk.Label(
                frame,
                text=self.t("app.no_ndef_fields"),
                style="SurfaceMuted.TLabel",
            ).grid(row=1, column=0, columnspan=5, sticky="w", padx=5, pady=8)
            return

        for index, item in enumerate(self.type2_fields):
            self._render_type2_row(index + 1, index, item)

    def _render_type2_row(
        self, row: int, index: int, item: dict[str, object]
    ) -> None:
        frame = self.ntag_fields_frame
        ttk.Label(
            frame,
            text=str(index + 1),
            style="SurfaceMuted.TLabel",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=4)

        name_var = item.get("name_var")
        if name_var is not None:
            ttk.Entry(frame, textvariable=name_var, width=24).grid(
                row=row, column=1, sticky="ew", padx=5, pady=4
            )
        else:
            ttk.Label(
                frame,
                text=self._type2_field_name(item),
                style="Surface.TLabel",
            ).grid(row=row, column=1, sticky="w", padx=5, pady=4)

        value_box = ttk.Frame(frame, style="Surface.TFrame")
        value_box.grid(row=row, column=2, sticky="ew", padx=5, pady=4)
        value_box.columnconfigure(0, weight=1)
        value_entry = ttk.Entry(value_box, textvariable=item["value_var"])
        value_entry.grid(row=0, column=0, sticky="ew")
        value_scroll = AutoHideScrollbar(
            value_box, orient="horizontal", command=value_entry.xview
        )
        value_scroll.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        value_entry.configure(xscrollcommand=value_scroll.set)
        write_name = ttk.Checkbutton(
            frame,
            variable=item["write_var"],
            style="Surface.TCheckbutton",
        )
        if item.get("kind") == "uri":
            item["write_var"].set(False)
            write_name.configure(state="disabled")
        write_name.grid(row=row, column=3, sticky="w", padx=5, pady=4)

        actions = ttk.Frame(frame, style="Surface.TFrame")
        actions.grid(row=row, column=4, sticky="e", padx=5, pady=4)
        up = ttk.Button(
            actions,
            text="↑",
            width=3,
            command=lambda current=index: self._move_type2_field(current, -1),
        )
        up.grid(row=0, column=0)
        if index == 0:
            up.configure(state="disabled")
        down = ttk.Button(
            actions,
            text="↓",
            width=3,
            command=lambda current=index: self._move_type2_field(current, 1),
        )
        down.grid(row=0, column=1, padx=(4, 0))
        if index == len(self.type2_fields) - 1:
            down.configure(state="disabled")
        ttk.Button(
            actions,
            text=self.t("common.remove"),
            image=self.theme.icon("cancel"),
            compound="left",
            command=lambda current=index: self._remove_type2_field(current),
        ).grid(row=0, column=2, padx=(6, 0))

    def _add_custom_field(self, kind: str = "text") -> None:
        normalized_kind = "uri" if kind == "uri" else "text"
        if normalized_kind == "uri" and any(
            item.get("kind") == "uri" for item in self.type2_fields
        ):
            self.dialogs.error(
                self.t("app.url_already_present_title"),
                self.t("app.url_already_present"),
            )
            return
        default_name_key = (
            "app.url_name" if normalized_kind == "uri" else "app.custom_field_default"
        )
        self.type2_fields.append(
            self._custom_type2_field(
                name=self.t(default_name_key),
                write_name=normalized_kind != "uri",
                kind=normalized_kind,
            )
        )
        self._render_type2_fields()
        self._sync_type2_scrollregion()

    def _move_type2_field(self, index: int, direction: int) -> None:
        target = index + direction
        if not (0 <= index < len(self.type2_fields)):
            return
        if not (0 <= target < len(self.type2_fields)):
            return
        self.type2_fields[index], self.type2_fields[target] = (
            self.type2_fields[target],
            self.type2_fields[index],
        )
        self._render_type2_fields()
        self._sync_type2_scrollregion()

    def _remove_type2_field(self, index: int) -> None:
        if 0 <= index < len(self.type2_fields):
            self.type2_fields.pop(index)
            self._render_type2_fields()
            self._sync_type2_scrollregion()

    def _collect_type2_fields(self) -> list[Type2Field]:
        return [
            Type2Field(
                self._type2_field_name(item),
                str(item["value_var"].get()),
                bool(item["write_var"].get()),
                kind=str(item.get("kind", "text")),
            )
            for item in self.type2_fields
        ]

    def _preview_ndef(self) -> bytes | None:
        try:
            fields = self._collect_type2_fields()
            tlv = build_type2_ndef(
                fields,
                language=self.locale,
                locale=self.locale,
                capacity=MAX_KNOWN_NDEF_CAPACITY,
            )
        except ValueError as exc:
            self.ndef_status_var.set(f"✕ {exc}")
            self.dialogs.error(self.t("app.invalid_ndef_title"), str(exc))
            return None
        pages = (len(tlv) + 3) // 4
        self.ndef_status_var.set(
            self.t(
                "app.ndef_valid_dynamic",
                bytes=len(tlv),
                pages=pages,
                last_page=3 + pages,
            )
        )
        return tlv
