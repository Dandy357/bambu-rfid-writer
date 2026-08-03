from __future__ import annotations

import os
import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import BOTH
from tkinter import ttk

from .domain.operation_events import UiEvent
from .i18n import Translator, language_choices, normalize_locale
from .material_library import MaterialNode
from .version import APP_NAME, APP_VERSION
from .infrastructure.settings import load_settings
from .pm3 import is_auto_port
from .sources import MfcSource
from .ui.callbacks import CallbackRegistry
from .ui.components.activity_bar import ActivityBar
from .ui.app_identity import apply_application_identity
from .ui.components.dialogs import ThemedDialogs
from .ui.components.mode_switcher import ModeSwitcher
from .ui.constants import MODE_CUID, MODE_SETTINGS, MODE_TYPE2
from .ui.material_library import MaterialLibraryMixin
from .ui.mifare_view import MifareViewMixin
from .ui.operations import OperationControllerMixin
from .ui.option_state import OperationSettingsMixin
from .ui.results import OperationResultsMixin
from .ui.settings_view import SettingsViewMixin
from .ui.theme import DARK, LIGHT, THEME_NAMES, ThemeManager
from .ui.type2_editor import Type2EditorMixin
from .ui.type2_view import Type2ViewMixin
from .ui.widgets import VerticalScrolledFrame


class WriterApp(
    OperationSettingsMixin,
    MifareViewMixin,
    Type2ViewMixin,
    SettingsViewMixin,
    MaterialLibraryMixin,
    Type2EditorMixin,
    OperationResultsMixin,
    OperationControllerMixin,
):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1180x900")
        self.root.minsize(860, 640)
        self.root.resizable(True, True)
        # Scrollbar visibility and wrapped labels may change child requested
        # sizes while the user drags a native window edge. Do not let those
        # requests push the top-level geometry back or move the resize border.
        self.root.pack_propagate(False)
        apply_application_identity(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.callbacks = CallbackRegistry(self.root)

        settings = load_settings()

        self.events: queue.Queue[UiEvent] = queue.Queue()
        self.busy = False
        self.busy_mode = MODE_CUID
        self.current_mode = settings.get("last_mode", MODE_CUID)
        if self.current_mode not in {MODE_CUID, MODE_TYPE2, MODE_SETTINGS}:
            self.current_mode = MODE_CUID
        self.loaded_source: MfcSource | None = None
        self.source_items: dict[str, MaterialNode] = {}
        self.library_nodes: list[MaterialNode] = []
        self.library_selected_path: Path | None = None
        self.mode_views: dict[str, dict[str, object]] = {}
        self.report_states = {
            MODE_CUID: {"text": "", "path": None},
            MODE_TYPE2: {"text": "", "path": None},
        }

        self.locale = normalize_locale(settings.get("language", "en"))
        self.tr = Translator(self.locale)
        self.t = self.tr.t
        self.language_pairs = language_choices()
        self.language_name_to_code = {name: code for code, name in self.language_pairs}
        self.language_code_to_name = {code: name for code, name in self.language_pairs}
        self.language_var = tk.StringVar(
            value=self.language_code_to_name.get(self.locale, self.locale)
        )
        saved_appearance = settings.get("appearance", LIGHT).strip().lower()
        self.appearance = saved_appearance if saved_appearance in THEME_NAMES else LIGHT
        self.appearance_var = tk.StringVar(value=self.appearance)
        self.theme = ThemeManager(self.root, self.appearance)
        self.dialogs = ThemedDialogs(self.root, self.theme, self.t)

        # No Proxmark path is shipped or inferred. A path only exists after the
        # user saves it in Settings.
        self.bundle_var = tk.StringVar(value=settings.get("bundle_root", ""))
        saved_port = settings.get("port", "AUTO")
        self.port_var = tk.StringVar(
            value=self.t("common.auto") if self._is_auto_port(saved_port) else saved_port
        )
        self.material_library_var = tk.StringVar(
            value=settings.get("material_library", "")
        )
        self.source_folder_var = tk.StringVar(value=settings.get("source_folder", ""))
        try:
            self.library_sash_position = max(150, int(settings.get("library_sash_position", "360")))
        except (TypeError, ValueError):
            self.library_sash_position = 360
        self._init_operation_settings(settings)
        self.cuid_verify_var = self.mfc_option_vars["verify_dump"]
        self.ntag_verify_var = self.ntag_option_vars["final_verify"]
        self.cancel_event = threading.Event()

        default_date = datetime.now().strftime("%m. %Y")
        self._init_type2_fields(settings, default_date=default_date)

        self.source_status_var = tk.StringVar()
        self.library_status_var = tk.StringVar()
        self.ndef_status_var = tk.StringVar()
        self.progress_var = tk.StringVar()
        self._reset_status_texts()

        self._configure_style()
        self._build_ui()
        self._poll_after_id: str | None = self.root.after(100, self._poll_events)

        if self.source_folder_var.get():
            self.source_status_var.set(self.t("app.source_pending_validation"))
            try:
                self.library_selected_path = Path(
                    self.source_folder_var.get()
                ).expanduser().resolve()
            except OSError:
                self.library_selected_path = None
        restored_library = self._restore_material_library_from_cache()
        if self.material_library_var.get() and not restored_library:
            self.library_status_var.set(self.t("app.library_ready_to_load"))

    @staticmethod
    def _is_auto_port(value: str | None) -> bool:
        return is_auto_port(value)

    def _reset_status_texts(self) -> None:
        self.source_status_var.set(self.t("app.source_prompt"))
        self.library_status_var.set(self.t("app.library_prompt"))
        self.ndef_status_var.set(self.t("app.ndef_prompt"))
        self.progress_var.set(self.t("app.ready"))

    def _configure_style(self) -> None:
        self.theme.name = self.appearance
        self.theme.apply()

    def _enable_dynamic_wrap(
        self, label: ttk.Label, *, minimum: int = 120
    ) -> ttk.Label:
        """Update wrapping after resize bursts instead of on every pixel."""

        state: dict[str, int] = {"width": minimum}

        def apply_width() -> None:
            try:
                width = max(minimum, state["width"] - 4)
                if int(float(label.cget("wraplength") or 0)) != width:
                    label.configure(wraplength=width)
            except (tk.TclError, TypeError, ValueError):
                return

        def schedule(event: tk.Event) -> None:
            state["width"] = max(1, int(event.width))
            self.callbacks.schedule(label, 45, apply_width, key="dynamic-wrap")

        label.bind("<Configure>", schedule, add="+")
        return label

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        self.mode_switcher = ModeSwitcher(
            outer,
            theme=self.theme,
            translate=self.t,
            command=self._select_mode,
            selected=self.current_mode,
        )
        self.mode_switcher.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.settings_button = self.mode_switcher.settings_button

        content = ttk.Frame(outer)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        self.cuid_mode = ttk.Frame(content)
        self.ntag_mode = ttk.Frame(content)
        self.settings_mode = ttk.Frame(content)

        self._build_mode(MODE_CUID, self.cuid_mode)
        self._build_mode(MODE_TYPE2, self.ntag_mode)
        self._build_settings_view(self.settings_mode)

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self.activity_bar = ActivityBar(
            footer,
            theme=self.theme,
            textvariable=self.progress_var,
        )
        self.activity_bar.grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.progress = self.activity_bar
        self.settings_save_button = ttk.Button(
            footer,
            text=self.t("common.save"),
            image=self.theme.icon("check"),
            compound="left",
            command=self._apply_settings_page,
        )
        self.settings_save_button.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.cancel_button = ttk.Button(
            footer,
            text=self.t("app.cancel_operation"),
            image=self.theme.icon("cancel"),
            compound="left",
            command=self._cancel_operation,
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=2, sticky="e")
        self._select_mode(self.current_mode, update_switcher=False)

    def _build_mode(self, mode: str, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        tabs = ttk.Notebook(parent)
        tabs.grid(row=0, column=0, sticky="nsew")
        write_tab = ttk.Frame(tabs)
        result_tab = ttk.Frame(tabs, padding=12)
        log_tab = ttk.Frame(tabs, padding=12)
        tabs.add(write_tab, text=self.t("app.tab_write"))
        tabs.add(result_tab, text=self.t("app.tab_result"))
        tabs.add(log_tab, text=self.t("app.tab_log"))

        write_tab.columnconfigure(0, weight=1)
        write_tab.rowconfigure(0, weight=1)
        if mode == MODE_CUID:
            write_scroller = VerticalScrolledFrame(
                write_tab,
                padding=12,
                background=self.theme.palette.window,
                fill_height=True,
            )
            write_scroller.grid(row=0, column=0, sticky="nsew")
            self.cuid_write_scroller = write_scroller
            content = write_scroller.content
            content.columnconfigure(0, weight=1)
            content.rowconfigure(1, weight=1)
            self._build_cuid_write_tab(content)
        else:
            write_scroller = VerticalScrolledFrame(
                write_tab,
                padding=16,
                background=self.theme.palette.window,
            )
            write_scroller.grid(row=0, column=0, sticky="nsew")
            self._build_type2_write_tab(write_scroller.content)

        view = self._build_result_and_log(mode, tabs, result_tab, log_tab)
        view["write_scroller"] = write_scroller
        self.mode_views[mode] = view

    def _select_mode(self, mode: str, *, update_switcher: bool = True) -> None:
        if mode not in {MODE_CUID, MODE_TYPE2, MODE_SETTINGS}:
            return
        if self.busy and mode == MODE_SETTINGS:
            return
        self.current_mode = mode
        targets = {
            MODE_CUID: self.cuid_mode,
            MODE_TYPE2: self.ntag_mode,
            MODE_SETTINGS: self.settings_mode,
        }
        for candidate_mode, frame in targets.items():
            if candidate_mode == mode:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()
        if hasattr(self, "settings_save_button"):
            if mode == MODE_SETTINGS:
                self.settings_save_button.grid()
            else:
                self.settings_save_button.grid_remove()
        if update_switcher and hasattr(self, "mode_switcher"):
            self.mode_switcher.select(mode, notify=False)

    def _toggle_theme(self) -> None:
        if self.busy:
            return
        self.appearance = LIGHT if self.appearance == DARK else DARK
        self.appearance_var.set(self.appearance)
        self._rebuild_ui()
        self._save_current_settings(show_error=True)

    def _rebuild_ui(self, *, selected_subtabs: dict[str, int] | None = None) -> None:
        selected_subtabs = selected_subtabs or {
            mode: int(
                self.mode_views[mode]["tabs"].index(
                    self.mode_views[mode]["tabs"].select()
                )
            )
            for mode in (MODE_CUID, MODE_TYPE2)
            if mode in self.mode_views
        }
        self.callbacks.cancel_all()
        if hasattr(self, "activity_bar"):
            self.activity_bar.stop()
        self.mode_views.clear()
        for child in self.root.winfo_children():
            child.destroy()
        self._configure_style()
        self._build_ui()
        if self.source_folder_var.get():
            self.source_status_var.set(self.t("app.source_pending_validation"))
        self._restore_material_library_view()
        for mode, index in selected_subtabs.items():
            try:
                self.mode_views[mode]["tabs"].select(index)
            except (tk.TclError, KeyError):
                pass
        self._select_mode(self.current_mode)


def _enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        return


def main() -> None:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    WriterApp(root)
    root.mainloop()
