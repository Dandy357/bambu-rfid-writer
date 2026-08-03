from __future__ import annotations

import os
from pathlib import Path
import webbrowser
import tkinter as tk
from tkinter import END, HORIZONTAL, LEFT, VERTICAL
from tkinter import ttk

from ..domain.write_reports import WriteReport
from ..domain import CheckItem, CommandResult, DiagnosticReport, NdefReadResult
from ..presentation.write_report import format_write_report
from ..presentation.ndef_read import format_ndef_read_result
from ..infrastructure.paths import diagnostic_log_directory
from ..presentation.diagnostic_report import (
    format_report,
    overall_label,
    state_label,
)
from ..writer import backup_directory
from .widgets import AutoHideScrollbar


class OperationResultsMixin:
    """Presentation behavior grouped by one GUI responsibility."""

    def _build_result_and_log(
        self,
        mode: str,
        tabs: ttk.Notebook,
        result_tab: ttk.Frame,
        log_tab: ttk.Frame,
    ) -> dict[str, object]:
        result_var = tk.StringVar(value=self.t("app.no_operation"))
        path_var = tk.StringVar(value="")
        result_tab.columnconfigure(0, weight=1)
        result_tab.rowconfigure(1, weight=1)
        top = ttk.Frame(result_tab)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(0, weight=1)
        result_label = self._enable_dynamic_wrap(
            ttk.Label(
                top,
                textvariable=result_var,
                style="Result.TLabel",
                justify="left",
            )
        )
        result_label.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        diagnostic_button = ttk.Button(
            top,
            text=self.t("app.check_cuid" if mode == "cuid" else "app.check_ndef"),
            image=self.theme.icon("diagnostic"),
            compound="left",
            command=lambda selected_mode=mode: self._start_diagnostic(selected_mode),
        )
        diagnostic_button.grid(row=0, column=1, sticky="e")

        tree_frame = ttk.Frame(result_tab)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            tree_frame,
            columns=("state", "detail"),
            show="tree headings",
            selectmode="browse",
        )
        tree.heading("#0", text=self.t("app.check"))
        tree.heading("state", text=self.t("app.status"))
        tree.heading("detail", text=self.t("app.details"))
        tree.column("#0", width=240, minwidth=160, stretch=False)
        tree.column("state", width=120, minwidth=95, stretch=False, anchor="center")
        tree.column("detail", width=1100, minwidth=320, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        tree_y_scroll = AutoHideScrollbar(
            tree_frame, orient=VERTICAL, command=tree.yview
        )
        tree_y_scroll.grid(row=0, column=1, sticky="ns")
        tree_x_scroll = AutoHideScrollbar(
            tree_frame, orient=HORIZONTAL, command=tree.xview
        )
        tree_x_scroll.grid(row=1, column=0, sticky="ew")
        tree.configure(
            yscrollcommand=tree_y_scroll.set,
            xscrollcommand=tree_x_scroll.set,
        )
        self.theme.configure_diagnostic_tree(tree)

        buttons = ttk.Frame(result_tab)
        buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        open_button = ttk.Button(
            buttons,
            text=self.t("app.open_report"),
            image=self.theme.icon("report"),
            compound="left",
            command=lambda selected_mode=mode: self._open_report(selected_mode),
            state="disabled",
        )
        open_button.pack(side=LEFT)
        ttk.Button(
            buttons,
            text=self.t("app.open_logs"),
            image=self.theme.icon("folder"),
            compound="left",
            command=self._open_log_directory,
        ).pack(side=LEFT, padx=(8, 0))
        ttk.Button(
            buttons,
            text=self.t("app.open_backups"),
            image=self.theme.icon("backup"),
            compound="left",
            command=self._open_backup_directory,
        ).pack(side=LEFT, padx=(8, 0))

        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)
        log_frame = ttk.Frame(log_tab)
        log_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_text = tk.Text(
            log_frame,
            wrap="none",
            font=("Consolas", 9),
        )
        self.theme.configure_log_text(log_text)
        log_text.grid(row=0, column=0, sticky="nsew")
        log_y_scroll = AutoHideScrollbar(
            log_frame, orient=VERTICAL, command=log_text.yview
        )
        log_y_scroll.grid(row=0, column=1, sticky="ns")
        log_x_scroll = AutoHideScrollbar(
            log_frame, orient=HORIZONTAL, command=log_text.xview
        )
        log_x_scroll.grid(row=1, column=0, sticky="ew")
        log_text.configure(
            yscrollcommand=log_y_scroll.set,
            xscrollcommand=log_x_scroll.set,
        )
        log_buttons = ttk.Frame(log_tab)
        log_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        log_buttons.columnconfigure(1, weight=1)
        ttk.Button(
            log_buttons,
            text=self.t("app.copy_report"),
            image=self.theme.icon("copy"),
            compound="left",
            command=lambda selected_mode=mode: self._copy_report(selected_mode),
        ).grid(row=0, column=0, sticky="w")
        path_label = self._enable_dynamic_wrap(
            ttk.Label(
                log_buttons,
                textvariable=path_var,
                style="Muted.TLabel",
                justify="right",
            ),
            minimum=180,
        )
        path_label.grid(row=0, column=1, sticky="ew", padx=(12, 0))

        state = self.report_states[mode]
        if state["text"]:
            self._insert_log_text(log_text, str(state["text"]))
        if state["path"]:
            path_var.set(str(state["path"]))
            open_button.configure(state="normal")

        return {
            "tabs": tabs,
            "result_tab": result_tab,
            "log_tab": log_tab,
            "result_var": result_var,
            "path_var": path_var,
            "tree": tree,
            "tree_x_scroll": tree_x_scroll,
            "tree_y_scroll": tree_y_scroll,
            "log_text": log_text,
            "log_x_scroll": log_x_scroll,
            "log_y_scroll": log_y_scroll,
            "open_button": open_button,
            "diagnostic_button": diagnostic_button,
        }

    @staticmethod
    def _log_tag_for_line(line: str) -> str | None:
        stripped = line.lstrip()
        if stripped.startswith("[+]"):
            return "pm3_ok"
        if stripped.startswith("[-]"):
            return "pm3_error"
        if stripped.startswith("[?]"):
            return "pm3_warning"
        if stripped.startswith("[=]"):
            return "pm3_info"
        if stripped.startswith("---") or stripped.startswith("==="):
            return "pm3_muted"
        return None

    def _insert_log_text(self, widget: tk.Text, text: str) -> None:
        for line in text.splitlines(keepends=True):
            tag = self._log_tag_for_line(line)
            if tag:
                widget.insert(END, line, tag)
            else:
                widget.insert(END, line)
        if text and not text.endswith("\n"):
            widget.insert(END, "\n")

    def _append_live_log(self, mode: str, text: str) -> None:
        if not text:
            return
        widget = self.mode_views[mode]["log_text"]
        self._insert_log_text(widget, text)
        widget.see(END)

    def _handle_live_event(self, mode: str, event: str, payload: object) -> None:
        if mode not in self.mode_views:
            return
        view = self.mode_views[mode]
        if event == "progress":
            self.progress_var.set(str(payload))
        elif event == "session_started":
            view["result_var"].set(self.t("app.live_session_started"))
        elif event == "command_started":
            self._append_live_log(
                mode,
                "\n" + self.t("app.live_command_started", command=str(payload)) + "\n"
                + "-" * 72,
            )
        elif event == "command_output":
            self._append_live_log(mode, str(payload))
        elif event == "command_finished" and isinstance(payload, CommandResult):
            self._append_live_log(
                mode,
                self.t(
                    "app.live_command_finished",
                    code=payload.returncode,
                    duration=payload.duration_seconds,
                    timeout=self.t("common.yes")
                    if payload.timed_out
                    else self.t("common.no"),
                ),
            )
        elif event == "check_added" and isinstance(payload, CheckItem):
            view["tree"].insert(
                "",
                END,
                text=payload.name,
                image=self.theme.status_icon(payload.state.value),
                values=(state_label(payload.state, self.locale), payload.detail),
                tags=(payload.state.value,),
            )
            view["result_var"].set(self.t("app.live_checks_updating"))
        elif event == "operation_finished":
            view["result_var"].set(self.t("app.live_finishing_report"))

    def _populate_checks(self, mode: str, checks: list[CheckItem]) -> None:
        tree = self.mode_views[mode]["tree"]
        for item in tree.get_children():
            tree.delete(item)
        for item in checks:
            tree.insert(
                "",
                END,
                text=item.name,
                image=self.theme.status_icon(item.state.value),
                values=(state_label(item.state, self.locale), item.detail),
                tags=(item.state.value,),
            )

    def _show_write_report(self, mode: str, report: WriteReport) -> None:
        self._finish_busy()
        view = self.mode_views[mode]
        text = format_write_report(report, self.locale)
        self.report_states[mode] = {"text": text, "path": report.report_path}
        prefix = (
            self.t("app.no_change_prefix")
            if report.no_change
            else self.t("app.success_prefix")
            if report.success
            else self.t("app.failure_prefix")
        )
        view["result_var"].set(prefix + report.summary)
        if report.success and report.verified is True:
            self.progress_var.set(self.t("app.operation_verified"))
            self.activity_bar.stop(state="success")
        elif report.success:
            self.progress_var.set(self.t("app.operation_completed_unverified"))
            self.activity_bar.stop(state="success")
        else:
            self.progress_var.set(self.t("app.operation_unverified"))
            self.activity_bar.stop(state="error")
        self._populate_checks(mode, report.checks)
        view["log_text"].delete("1.0", END)
        self._insert_log_text(view["log_text"], text)
        if report.report_path:
            view["path_var"].set(str(report.report_path))
            view["open_button"].configure(state="normal")
        view["tabs"].select(view["result_tab"])
        self._select_mode(mode)
        if report.success:
            self.dialogs.info(self.t("app.operation_done_title"), report.summary)
        else:
            self.dialogs.error(
                self.t("app.write_failed_title"),
                self.t("app.write_failed_detail", summary=report.summary),
            )

    def _show_diagnostic_report(self, mode: str, report: DiagnosticReport) -> None:
        self._finish_busy()
        view = self.mode_views[mode]
        text = format_report(report, self.locale)
        self.report_states[mode] = {"text": text, "path": report.report_path}
        view["result_var"].set(
            f"{overall_label(report.overall_state, self.locale)} — {report.summary}"
        )
        self.progress_var.set(self.t("app.diagnostic_done"))
        self.activity_bar.stop(state="success")
        self._populate_checks(mode, report.checks)
        view["log_text"].delete("1.0", END)
        self._insert_log_text(view["log_text"], text)
        if report.report_path:
            view["path_var"].set(str(report.report_path))
            view["open_button"].configure(state="normal")
        view["tabs"].select(view["result_tab"])
        self._select_mode(mode)

    def _show_ndef_read_result(self, result: NdefReadResult) -> None:
        self._finish_busy()
        self.progress_var.set(self.t("app.read_ndef_done"))
        self.activity_bar.stop(state="success")
        text = format_ndef_read_result(result, self.locale)
        self.dialogs.text_info(
            self.t("app.read_ndef_result_title"),
            self.t("app.read_ndef_result_summary"),
            text,
        )

    def _show_fatal(self, mode: str, message: str, details: str) -> None:
        self._finish_busy()
        view = self.mode_views[mode]
        self.progress_var.set(self.t("app.application_failed"))
        self.activity_bar.stop(state="error")
        view["result_var"].set(f"{self.t('state.error')} — {message}")
        self.report_states[mode] = {"text": details, "path": None}
        view["log_text"].delete("1.0", END)
        self._insert_log_text(view["log_text"], details)
        view["tabs"].select(view["log_tab"])
        self._select_mode(mode)
        self.dialogs.error(self.t("app.operation_failed_title"), message)

    def _copy_report(self, mode: str) -> None:
        view = self.mode_views[mode]
        text = str(self.report_states[mode]["text"]) or view["log_text"].get("1.0", END).strip()
        if not text:
            self.dialogs.info(self.t("app.report_title"), self.t("app.nothing_to_copy"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.progress_var.set(self.t("app.report_copied"))

    def _open_report(self, mode: str) -> None:
        path = self.report_states[mode]["path"]
        if isinstance(path, Path):
            self._open_path(path)

    def _open_log_directory(self) -> None:
        directory = diagnostic_log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        self._open_path(directory)

    def _open_backup_directory(self) -> None:
        directory = backup_directory()
        directory.mkdir(parents=True, exist_ok=True)
        self._open_path(directory)

    @staticmethod
    def _open_path(path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.as_uri())
