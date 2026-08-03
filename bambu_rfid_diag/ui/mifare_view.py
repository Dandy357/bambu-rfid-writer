from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .widgets import AutoHideScrollbar


class MifareViewMixin:
    """Build the Bambu MIFARE Classic source and write screen."""

    def _build_cuid_write_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        summary = ttk.Frame(tab, style="Card.TFrame", padding=10)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.cuid_summary_card = summary
        summary.columnconfigure(0, weight=1)
        self._enable_dynamic_wrap(
            ttk.Label(
                summary,
                textvariable=self.library_status_var,
                style="SurfaceMuted.TLabel",
                justify="left",
            )
        ).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.library_refresh_button = ttk.Button(
            summary,
            text=self.t("app.refresh_library"),
            image=self.theme.icon("folder"),
            compound="left",
            command=lambda: self._load_material_library(True),
        )
        self.library_refresh_button.grid(row=0, column=1, sticky="e")

        self.library_paned = ttk.Panedwindow(tab, orient=tk.VERTICAL)
        self.library_paned.grid(row=1, column=0, sticky="nsew")

        tree_card = ttk.Frame(self.library_paned, style="Card.TFrame", padding=10)
        tree_card.columnconfigure(0, weight=1)
        tree_card.rowconfigure(1, weight=1)
        ttk.Label(
            tree_card,
            text=self.t("app.library_tree_heading"),
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 7))

        tree_frame = ttk.Frame(tree_card, style="Card.TFrame", padding=1)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.material_tree = ttk.Treeview(
            tree_frame,
            columns=("kind", "uid"),
            show="tree headings",
            selectmode="browse",
        )
        self.material_tree.heading("#0", text=self.t("app.material_column"))
        self.material_tree.heading("kind", text=self.t("app.item_type"))
        self.material_tree.heading("uid", text="UID")
        self.material_tree.column("#0", width=520, minwidth=260, stretch=True)
        self.material_tree.column("kind", width=150, minwidth=115, stretch=False)
        self.material_tree.column("uid", width=130, minwidth=105, stretch=False)
        self.material_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = AutoHideScrollbar(
            tree_frame, orient="vertical", command=self.material_tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.material_tree.configure(yscrollcommand=scrollbar.set)
        self.material_tree.bind("<<TreeviewSelect>>", self._on_material_selected)
        self.material_tree.tag_configure("ready", foreground=self.theme.palette.ok)
        self.material_tree.tag_configure(
            "warning", foreground=self.theme.palette.warning
        )
        self.material_tree.tag_configure("invalid", foreground=self.theme.palette.error)
        self.material_tree.tag_configure(
            "unverified", foreground=self.theme.palette.skipped
        )

        column_resize_state: dict[str, object] = {
            "width": 0,
            "applied": None,
        }

        def apply_material_columns() -> None:
            available = max(620, int(column_resize_state["width"]) - 22)
            kind_width = 145
            uid_width = 125
            widths = (
                max(330, available - kind_width - uid_width),
                kind_width,
                uid_width,
            )
            if column_resize_state["applied"] == widths:
                return
            column_resize_state["applied"] = widths
            self.material_tree.column("#0", width=widths[0])
            self.material_tree.column("kind", width=widths[1])
            self.material_tree.column("uid", width=widths[2])

        def schedule_material_columns(event: tk.Event) -> None:
            column_resize_state["width"] = max(1, int(event.width))
            self.callbacks.schedule(
                tree_frame,
                45,
                apply_material_columns,
                key="material-columns",
            )

        tree_frame.bind("<Configure>", schedule_material_columns, add="+")

        detail_card = ttk.Frame(self.library_paned, style="Card.TFrame", padding=12)
        detail_card.columnconfigure(0, weight=1)
        self.cuid_write_content = tab
        self.cuid_detail_card = detail_card
        self.cuid_sash_extent = 6

        selection = ttk.Frame(detail_card, style="Surface.TFrame")
        selection.grid(row=0, column=0, sticky="ew")
        selection.columnconfigure(0, weight=1)
        self._enable_dynamic_wrap(
            ttk.Label(
                selection,
                textvariable=self.source_status_var,
                style="Surface.TLabel",
                justify="left",
            )
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            selection,
            text=self.t("app.choose_single_source"),
            image=self.theme.icon("folder"),
            compound="left",
            command=self._choose_source,
        ).grid(row=0, column=1, sticky="e", padx=(10, 0))

        self._enable_dynamic_wrap(
            ttk.Label(
                detail_card,
                text=self.t("app.cuid_process"),
                style="SurfaceMuted.TLabel",
                justify="left",
            )
        ).grid(row=1, column=0, sticky="ew", pady=(10, 10))

        actions = ttk.Frame(detail_card, style="Surface.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        actions.columnconfigure(3, weight=1)
        self.bambu_write_button = ttk.Button(
            actions,
            text=self.t("app.write_bambu"),
            image=self.theme.icon("write", inverse=True),
            compound="left",
            style="CuidAccent.TButton",
            command=self._start_bambu_write,
            cursor="hand2",
        )
        self.bambu_write_button.grid(row=0, column=0, sticky="w")
        self.cuid_check_button = ttk.Button(
            actions,
            text=self.t("app.check_cuid"),
            image=self.theme.icon("diagnostic"),
            compound="left",
            command=lambda: self._start_diagnostic("cuid"),
        )
        self.cuid_check_button.grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Checkbutton(
            actions,
            text=self.t("app.verify_after_write"),
            variable=self.cuid_verify_var,
            command=self._sync_cuid_quick_verify,
        ).grid(row=0, column=2, sticky="w", padx=(16, 0))
        self._enable_dynamic_wrap(
            ttk.Label(
                actions,
                text=self.t("app.configurable_checks_note"),
                style="SurfaceMuted.TLabel",
                justify="left",
            ),
            minimum=180,
        ).grid(row=0, column=3, sticky="ew", padx=(16, 0))

        self.library_paned.add(tree_card, weight=3)
        self.library_paned.add(detail_card, weight=2)
        self.cuid_detail_card.bind(
            "<Configure>", self._schedule_cuid_scroll_layout, add="+"
        )
        self.library_paned.bind(
            "<Configure>", self._schedule_library_sash_apply, add="+"
        )
        self.library_paned.bind(
            "<B1-Motion>", self._on_library_sash_motion, add="+"
        )
        self.library_paned.bind(
            "<ButtonRelease-1>", self._remember_library_sash, add="+"
        )
        self.callbacks.idle(
            self.library_paned,
            self._restore_library_sash,
            key="restore-library-sash",
        )

    def _restore_library_sash(self) -> None:
        if not hasattr(self, "library_paned"):
            return
        self._schedule_cuid_scroll_layout()
        self._schedule_library_sash_apply()

    def _capture_library_sash_position(self, event: object | None = None) -> None:
        candidate = getattr(event, "y", None)
        if candidate is None:
            try:
                candidate = self.library_paned.sashpos(0)
            except tk.TclError:
                return
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            return
        if value > 0:
            self.library_sash_position = max(150, value)

    def _schedule_library_sash_apply(self, _event: object | None = None) -> None:
        if not hasattr(self, "library_paned"):
            return
        self.callbacks.schedule(
            self.library_paned,
            30,
            self._apply_library_sash_position,
            key="apply-library-sash",
        )

    def _apply_library_sash_position(self) -> None:
        try:
            self.library_paned.sashpos(0, max(150, self.library_sash_position))
            actual = int(self.library_paned.sashpos(0))
            detail_y = int(self.cuid_detail_card.winfo_y())
            if detail_y > actual:
                self.cuid_sash_extent = max(1, detail_y - actual)
        except tk.TclError:
            return

    def _on_library_sash_motion(self, event: object) -> None:
        self._capture_library_sash_position(event)
        self._schedule_cuid_scroll_layout()

    def _schedule_cuid_scroll_layout(self, _event: object | None = None) -> None:
        if not hasattr(self, "library_paned"):
            return
        self.callbacks.schedule(
            self.library_paned,
            20,
            self._sync_cuid_scroll_layout,
            key="cuid-scroll-layout",
        )

    def _sync_cuid_scroll_layout(self) -> None:
        required = (
            max(150, int(self.library_sash_position))
            + int(self.cuid_sash_extent)
            + int(self.cuid_detail_card.winfo_reqheight())
        )
        self.cuid_write_content.rowconfigure(1, minsize=required)
        # The outer CUID content frame has 12 px padding on both sides and the
        # summary card has a 10 px lower gap. Build the minimum from those
        # logical requirements instead of winfo_reqheight(), because a
        # Panedwindow can remember a formerly allocated height and otherwise
        # leave a blank scrollable tail after shrinking.
        content_min_height = (
            24
            + int(self.cuid_summary_card.winfo_reqheight())
            + 10
            + required
        )
        self.cuid_write_scroller.set_content_min_height(content_min_height)
        self._schedule_library_sash_apply()

    def _remember_library_sash(self, event: object | None = None) -> None:
        if not hasattr(self, "library_paned"):
            return
        self._capture_library_sash_position(event)
        self._schedule_cuid_scroll_layout()
        self._save_current_settings()
