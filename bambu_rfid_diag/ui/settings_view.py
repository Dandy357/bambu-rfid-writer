from __future__ import annotations

import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk

from ..i18n import Translator, normalize_locale
from ..version import APP_NAME, APP_VERSION
from ..options import (
    NTAG_METHOD_RAW,
    NTAG_METHOD_RESTORE,
    NTAG_METHOD_WRBL,
    PROFILE_CUSTOM,
    PROFILE_FAST,
    PROFILE_RECOMMENDED,
    PROFILE_THOROUGH,
    mfc_profile,
    type2_erase_profile,
    type2_write_profile,
)
from ..pm3 import BundleValidationError, resolve_bundle, validate_port
from ..infrastructure.paths import app_data_directory, clear_user_data_directory
from ..infrastructure.settings import save_settings
from .constants import MODE_CUID, MODE_SETTINGS, MODE_TYPE2
from .theme import DARK, LIGHT
from .widgets import VerticalScrolledFrame


LOGGER = logging.getLogger(__name__)


class SettingsViewMixin:
    """Build and apply the persistent Settings page."""

    def _open_settings(self) -> None:
        if not self.busy:
            self._select_mode(MODE_SETTINGS)

    def _build_settings_view(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        outer = ttk.Frame(parent, padding=(0, 4, 0, 0))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.settings_notebook = notebook

        self.settings_status_var = tk.StringVar(value="")
        self.settings_language_display_var = tk.StringVar(value=self.language_var.get())
        self.settings_appearance_display_var = tk.StringVar(
            value=(
                self.t("settings.appearance_dark")
                if self.appearance == DARK
                else self.t("settings.appearance_light")
            )
        )

        def tab_frame(title_key: str) -> ttk.Frame:
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=self.t(title_key))
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)
            scroller = VerticalScrolledFrame(
                tab,
                padding=14,
                background=self.theme.palette.window,
            )
            scroller.grid(row=0, column=0, sticky="nsew")
            scroller.content.columnconfigure(0, weight=1)
            return scroller.content

        self._build_general_settings_tab(tab_frame("settings.general_tab"))
        self._build_cuid_settings_tab(tab_frame("settings.cuid_tab"))
        self._build_type2_write_settings_tab(tab_frame("settings.ntag_write_tab"))
        self._build_type2_erase_settings_tab(tab_frame("settings.ntag_erase_tab"))
        self._build_timeout_settings_tab(tab_frame("settings.timeouts_tab"))

        status = self._enable_dynamic_wrap(
            ttk.Label(
                outer,
                textvariable=self.settings_status_var,
                style="DangerText.TLabel",
                justify="left",
            )
        )
        status.grid(row=1, column=0, sticky="ew", pady=(8, 0))


    def _settings_card(self, parent: ttk.Frame, title: str, row: int) -> ttk.Frame:
        card = ttk.LabelFrame(
            parent,
            text=title,
            padding=12,
            style="Card.TLabelframe",
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.columnconfigure(1, weight=1)
        return card

    def _build_general_settings_tab(self, parent: ttk.Frame) -> None:
        appearance = self._settings_card(
            parent, self.t("settings.general_section"), 0
        )
        ttk.Label(
            appearance, text=self.t("app.language"), style="Surface.TLabel"
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Combobox(
            appearance,
            textvariable=self.settings_language_display_var,
            values=[name for _code, name in self.language_pairs],
            state="readonly",
            width=22,
        ).grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(
            appearance,
            text=self.t("settings.appearance"),
            style="Surface.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Combobox(
            appearance,
            textvariable=self.settings_appearance_display_var,
            values=[
                self.t("settings.appearance_light"),
                self.t("settings.appearance_dark"),
            ],
            state="readonly",
            width=22,
        ).grid(row=1, column=1, sticky="w", pady=5)

        connection = self._settings_card(
            parent, self.t("settings.connection_section"), 1
        )
        ttk.Label(
            connection,
            text=self.t("app.bundle_folder"),
            style="Surface.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(connection, textvariable=self.bundle_var).grid(
            row=0, column=1, sticky="ew", pady=5
        )
        ttk.Button(
            connection,
            text=self.t("common.choose"),
            image=self.theme.icon("folder"),
            compound="left",
            command=self._choose_bundle_from_settings,
        ).grid(row=0, column=2, padx=(8, 0), pady=5)
        ttk.Label(
            connection, text=self.t("app.com_port"), style="Surface.TLabel"
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        ports = [self.t("common.auto")] + [f"COM{number}" for number in range(1, 101)]
        ttk.Combobox(
            connection,
            textvariable=self.port_var,
            values=ports,
            width=20,
        ).grid(row=1, column=1, sticky="w", pady=5)
        self._enable_dynamic_wrap(
            ttk.Label(
                connection,
                text=self.t("app.settings_no_default"),
                style="SurfaceMuted.TLabel",
                justify="left",
            )
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        library = self._settings_card(
            parent, self.t("settings.library_section"), 2
        )
        ttk.Label(
            library,
            text=self.t("app.library_folder"),
            style="Surface.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(library, textvariable=self.material_library_var).grid(
            row=0, column=1, sticky="ew", pady=5
        )
        ttk.Button(
            library,
            text=self.t("common.choose"),
            image=self.theme.icon("folder"),
            compound="left",
            command=self._choose_library,
        ).grid(row=0, column=2, padx=(8, 0), pady=5)
        self.library_load_button = ttk.Button(
            library,
            text=self.t("app.load_library"),
            command=lambda: self._load_material_library(True),
        )
        self.library_load_button.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self._enable_dynamic_wrap(
            ttk.Label(
                library,
                textvariable=self.library_status_var,
                style="SurfaceMuted.TLabel",
                justify="left",
            )
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(9, 0))

        user_data = self._settings_card(
            parent, self.t("settings.user_data_section"), 3
        )
        user_data.columnconfigure(0, weight=1)
        self._enable_dynamic_wrap(
            ttk.Label(
                user_data,
                text=self.t(
                    "settings.user_data_description",
                    path=str(app_data_directory()),
                ),
                style="SurfaceMuted.TLabel",
                justify="left",
            )
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.clear_user_data_button = ttk.Button(
            user_data,
            text=self.t("settings.clear_user_data"),
            image=self.theme.icon("erase", inverse=True),
            compound="left",
            style="Danger.TButton",
            command=self._clear_user_data,
        )
        self.clear_user_data_button.grid(row=1, column=0, sticky="w")

        about = self._settings_card(parent, self.t("settings.about_section"), 4)
        ttk.Label(
            about,
            text=f"{APP_NAME} {APP_VERSION}",
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        self._enable_dynamic_wrap(
            ttk.Label(
                about,
                text=self.t("settings.about_description"),
                style="SurfaceMuted.TLabel",
                justify="left",
            )
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))


    def _clear_user_data(self) -> None:
        """Delete all per-user files and exit without recreating settings."""

        if self.busy:
            return
        data_path = app_data_directory()
        confirmed = self.dialogs.confirm(
            self.t("settings.clear_user_data_title"),
            self.t("settings.clear_user_data_confirm", path=str(data_path)),
            accent="type2",
            destructive=True,
        )
        if not confirmed:
            return
        final_confirmed = self.dialogs.confirm(
            self.t("settings.clear_user_data_final_title"),
            self.t("settings.clear_user_data_final_confirm"),
            accent="type2",
            destructive=True,
        )
        if not final_confirmed:
            return
        try:
            clear_user_data_directory()
        except OSError as exc:
            LOGGER.exception("Failed to delete application user data")
            self.dialogs.error(
                self.t("settings.clear_user_data_failed_title"),
                self.t("settings.clear_user_data_failed", error=str(exc)),
            )
            return
        self.callbacks.cancel_all()
        self.root.destroy()

    def _choose_bundle_from_settings(self) -> None:
        initial = self.bundle_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(
            title=self.t("app.choose_bundle_title"),
            initialdir=initial if Path(initial).exists() else str(Path.home()),
            mustexist=True,
            parent=self.root,
        )
        if selected:
            self.bundle_var.set(selected)

    def _profile_metadata(self):
        profile_codes = (
            PROFILE_FAST,
            PROFILE_RECOMMENDED,
            PROFILE_THOROUGH,
            PROFILE_CUSTOM,
        )
        labels = {code: self.t(f"settings.profile_{code}") for code in profile_codes}
        return profile_codes, labels, {label: code for code, label in labels.items()}

    def _profile_combo(
        self,
        parent: ttk.Frame,
        code_var: tk.StringVar,
        apply_callback,
        *,
        row: int = 0,
    ) -> None:
        _codes, labels, reverse = self._profile_metadata()
        shown = tk.StringVar(value=labels.get(code_var.get(), labels[PROFILE_CUSTOM]))
        if not hasattr(self, "_profile_display_vars"):
            self._profile_display_vars = {}
        self._profile_display_vars[id(code_var)] = shown
        ttk.Label(
            parent, text=self.t("settings.profile"), style="Surface.TLabel"
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        combo = ttk.Combobox(
            parent,
            textvariable=shown,
            values=list(labels.values()),
            state="readonly",
            width=25,
        )
        combo.grid(row=row, column=1, sticky="w", pady=(0, 8))

        def changed(_event=None) -> None:
            code = reverse.get(shown.get(), PROFILE_CUSTOM)
            code_var.set(code)
            apply_callback(code)

        combo.bind("<<ComboboxSelected>>", changed)

    def _method_combo(
        self,
        parent: ttk.Frame,
        code_var: tk.StringVar,
        row: int,
        profile_var: tk.StringVar,
    ) -> None:
        codes = (NTAG_METHOD_RAW, NTAG_METHOD_RESTORE, NTAG_METHOD_WRBL)
        labels = {code: self.t(f"settings.method_{code}") for code in codes}
        reverse = {label: code for code, label in labels.items()}
        shown = tk.StringVar(value=labels.get(code_var.get(), labels[NTAG_METHOD_RAW]))
        ttk.Label(
            parent, text=self.t("settings.write_method"), style="Surface.TLabel"
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        combo = ttk.Combobox(
            parent,
            textvariable=shown,
            values=list(labels.values()),
            state="readonly",
            width=38,
        )
        combo.grid(row=row, column=1, sticky="w", pady=(0, 8))
        def changed(_event=None) -> None:
            code_var.set(reverse.get(shown.get(), NTAG_METHOD_RAW))
            profile_var.set(PROFILE_CUSTOM)
            profile_display = getattr(self, "_profile_display_vars", {}).get(
                id(profile_var)
            )
            if profile_display is not None:
                profile_display.set(self.t("settings.profile_custom"))

        combo.bind("<<ComboboxSelected>>", changed)

    def _check_group(
        self,
        parent: ttk.Frame,
        title_key: str,
        items: list[tuple[str, tk.BooleanVar]],
        row: int,
        profile_var: tk.StringVar,
    ) -> int:
        frame = ttk.LabelFrame(
            parent,
            text=self.t(title_key),
            padding=10,
            style="Card.TLabelframe",
        )
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        def custom() -> None:
            profile_var.set(PROFILE_CUSTOM)
            shown = getattr(self, "_profile_display_vars", {}).get(id(profile_var))
            if shown is not None:
                shown.set(self.t("settings.profile_custom"))

        for index, (label_key, variable) in enumerate(items):
            ttk.Checkbutton(
                frame,
                text=self.t(label_key),
                variable=variable,
                command=custom,
            ).grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, 18),
                pady=3,
            )
        return row + 1

    def _apply_mfc_profile_to_vars(self, code: str) -> None:
        if code == PROFILE_CUSTOM:
            return
        preset = mfc_profile(code)
        values = {
            "source_dump_size": preset.source.dump_size,
            "source_key_size": preset.source.key_size,
            "source_bcc": preset.source.bcc,
            "source_trailer_keys": preset.source.trailer_keys,
            "source_access_bits": preset.source.access_bits,
            "source_filename_uid": preset.source.filename_uid,
            "client_firmware": preset.client_firmware,
            "tag_type": preset.tag_type,
            "magic_type": preset.magic_type,
            "default_keys": preset.default_keys,
            "backup": preset.backup,
            "target_stability": preset.target_stability,
            "verify_dump": preset.verify_dump,
            "verify_uid": preset.verify_uid,
        }
        for key, value in values.items():
            self.mfc_option_vars[key].set(value)

    def _build_cuid_settings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._profile_combo(
            parent, self.mfc_profile_var, self._apply_mfc_profile_to_vars
        )
        self._enable_dynamic_wrap(
            ttk.Label(
                parent,
                text=self.t("settings.fast_profile_note"),
                style="Muted.TLabel",
                justify="left",
            )
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        row = self._check_group(
            parent,
            "settings.source_checks",
            [
                ("settings.mfc_dump_size", self.mfc_option_vars["source_dump_size"]),
                ("settings.mfc_key_size", self.mfc_option_vars["source_key_size"]),
                ("settings.mfc_bcc", self.mfc_option_vars["source_bcc"]),
                ("settings.mfc_trailer_keys", self.mfc_option_vars["source_trailer_keys"]),
                ("settings.mfc_access_bits", self.mfc_option_vars["source_access_bits"]),
                ("settings.mfc_filename_uid", self.mfc_option_vars["source_filename_uid"]),
            ],
            2,
            self.mfc_profile_var,
        )
        row = self._check_group(
            parent,
            "settings.target_checks",
            [
                ("settings.client_firmware", self.mfc_option_vars["client_firmware"]),
                ("settings.mfc_tag_type", self.mfc_option_vars["tag_type"]),
                ("settings.magic_type", self.mfc_option_vars["magic_type"]),
                ("settings.default_keys", self.mfc_option_vars["default_keys"]),
                ("settings.backup", self.mfc_option_vars["backup"]),
                ("settings.target_stability", self.mfc_option_vars["target_stability"]),
            ],
            row,
            self.mfc_profile_var,
        )
        self._check_group(
            parent,
            "settings.after_write",
            [
                ("settings.verify_dump", self.mfc_option_vars["verify_dump"]),
                ("settings.verify_uid", self.mfc_option_vars["verify_uid"]),
            ],
            row,
            self.mfc_profile_var,
        )

    def _apply_type2_write_profile_to_vars(self, code: str) -> None:
        if code == PROFILE_CUSTOM:
            return
        preset = type2_write_profile(code)
        self.ntag_method_var.set(preset.method)
        for key, var in self.ntag_option_vars.items():
            var.set(getattr(preset, key))

    def _build_type2_write_settings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._profile_combo(
            parent, self.ntag_profile_var, self._apply_type2_write_profile_to_vars
        )
        self._method_combo(
            parent, self.ntag_method_var, 1, self.ntag_profile_var
        )
        self._enable_dynamic_wrap(
            ttk.Label(
                parent,
                text=self.t("settings.fast_profile_note"),
                style="Muted.TLabel",
                justify="left",
            )
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        row = self._check_group(
            parent,
            "settings.target_checks",
            [
                ("settings.client_firmware", self.ntag_option_vars["client_firmware"]),
                ("settings.ntag_tag_type", self.ntag_option_vars["tag_type"]),
                ("settings.static_lock", self.ntag_option_vars["static_lock"]),
                ("settings.dynamic_lock", self.ntag_option_vars["dynamic_lock"]),
                ("settings.auth0", self.ntag_option_vars["auth0"]),
                ("settings.ecc_signature", self.ntag_option_vars["ecc_signature"]),
                ("settings.backup", self.ntag_option_vars["backup"]),
                ("settings.target_stability", self.ntag_option_vars["target_stability"]),
            ],
            3,
            self.ntag_profile_var,
        )
        self._check_group(
            parent,
            "settings.write_process",
            [
                ("settings.two_phase", self.ntag_option_vars["two_phase"]),
                ("settings.precommit_verify", self.ntag_option_vars["precommit_verify"]),
                ("settings.final_verify", self.ntag_option_vars["final_verify"]),
                ("settings.protected_verify", self.ntag_option_vars["protected_verify"]),
            ],
            row,
            self.ntag_profile_var,
        )

    def _apply_type2_erase_profile_to_vars(self, code: str) -> None:
        if code == PROFILE_CUSTOM:
            return
        preset = type2_erase_profile(code)
        self.erase_method_var.set(preset.method)
        for key, var in self.erase_option_vars.items():
            var.set(getattr(preset, key))

    def _build_type2_erase_settings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        self._profile_combo(
            parent, self.erase_profile_var, self._apply_type2_erase_profile_to_vars
        )
        self._method_combo(
            parent, self.erase_method_var, 1, self.erase_profile_var
        )
        self._enable_dynamic_wrap(
            ttk.Label(
                parent,
                text=self.t("settings.fast_profile_note"),
                style="Muted.TLabel",
                justify="left",
            )
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        row = self._check_group(
            parent,
            "settings.target_checks",
            [
                ("settings.client_firmware", self.erase_option_vars["client_firmware"]),
                ("settings.ntag_tag_type", self.erase_option_vars["tag_type"]),
                ("settings.static_lock", self.erase_option_vars["static_lock"]),
                ("settings.dynamic_lock", self.erase_option_vars["dynamic_lock"]),
                ("settings.auth0", self.erase_option_vars["auth0"]),
                ("settings.ecc_signature", self.erase_option_vars["ecc_signature"]),
                ("settings.backup", self.erase_option_vars["backup"]),
                ("settings.target_stability", self.erase_option_vars["target_stability"]),
            ],
            3,
            self.erase_profile_var,
        )
        self._check_group(
            parent,
            "settings.erase_process",
            [
                ("settings.scan_nonzero", self.erase_option_vars["scan_nonzero_pages"]),
                ("settings.final_verify", self.erase_option_vars["final_verify"]),
                ("settings.protected_verify", self.erase_option_vars["protected_verify"]),
            ],
            row,
            self.erase_profile_var,
        )

    def _build_timeout_settings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        rows = [
            ("startup", "settings.timeout_startup"),
            ("idle", "settings.timeout_idle"),
            ("command", "settings.timeout_command"),
            ("operation", "settings.timeout_operation"),
        ]
        for row, (key, label_key) in enumerate(rows):
            ttk.Label(parent, text=self.t(label_key)).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=6
            )
            ttk.Entry(parent, textvariable=self.timeout_vars[key], width=12).grid(
                row=row, column=1, sticky="w", pady=6
            )
        self._enable_dynamic_wrap(
            ttk.Label(
                parent,
                text=self.t("settings.timeout_zero"),
                style="Muted.TLabel",
                justify="left",
            )
        ).grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _apply_settings_page(self) -> None:
        self.settings_status_var.set("")
        bundle = self.bundle_var.get().strip()
        if bundle:
            try:
                layout = resolve_bundle(bundle, self.locale)
            except BundleValidationError as exc:
                self.settings_status_var.set(str(exc))
                return
            self.bundle_var.set(str(layout.root))
        try:
            port = validate_port(self.port_var.get(), self.locale)
            self._current_timeouts()
        except ValueError as exc:
            self.settings_status_var.set(str(exc))
            return
        self.port_var.set(self.t("common.auto") if port is None else port)

        new_locale = self.language_name_to_code.get(
            self.settings_language_display_var.get(), self.locale
        )
        new_appearance = (
            DARK
            if self.settings_appearance_display_var.get()
            == self.t("settings.appearance_dark")
            else LIGHT
        )
        locale_changed = new_locale != self.locale
        appearance_changed = new_appearance != self.appearance
        self.appearance = new_appearance
        self.appearance_var.set(new_appearance)

        if locale_changed:
            self._change_language(new_locale)
        elif appearance_changed:
            self._rebuild_ui()
            self._save_current_settings(show_error=True)
        else:
            if self._save_current_settings(show_error=True):
                self.settings_status_var.set(self.t("settings.saved"))

    def _change_language(self, new_locale: str) -> None:
        selected_subtabs = {
            mode: int(
                self.mode_views[mode]["tabs"].index(
                    self.mode_views[mode]["tabs"].select()
                )
            )
            for mode in (MODE_CUID, MODE_TYPE2)
            if mode in self.mode_views
        }
        was_auto = self._is_auto_port(self.port_var.get())
        self.locale = normalize_locale(new_locale)
        self._prepare_material_library_for_locale_change()
        self.tr = Translator(self.locale)
        self.t = self.tr.t
        self.language_var.set(self.language_code_to_name.get(self.locale, self.locale))
        if was_auto:
            self.port_var.set(self.t("common.auto"))
        self._reset_status_texts()
        self._rebuild_ui(selected_subtabs=selected_subtabs)
        self._save_current_settings(show_error=True)

    def _current_settings_values(self) -> dict[str, str]:
        """Return the complete persistent GUI state without writing it."""

        values = {
            "language": self.locale,
            "appearance": self.appearance,
            "bundle_root": self.bundle_var.get().strip(),
            "port": (
                "AUTO"
                if self._is_auto_port(self.port_var.get())
                else self.port_var.get().strip()
            ),
            "material_library": self.material_library_var.get().strip(),
            "source_folder": self.source_folder_var.get().strip(),
            "last_mode": self.current_mode,
            "library_sash_position": str(self.library_sash_position),
            "mfc_profile": self.mfc_profile_var.get(),
            "ntag_profile": self.ntag_profile_var.get(),
            "erase_profile": self.erase_profile_var.get(),
            "ntag_method": self.ntag_method_var.get(),
            "erase_method": self.erase_method_var.get(),
            "ntag_brand": self.brand_var.get(),
            "ntag_filament": self.filament_var.get(),
            "ntag_purchase": self.purchase_var.get(),
            "ntag_url": self.url_var.get(),
            "ntag_brand_write_name": "1" if self.brand_name_var.get() else "0",
            "ntag_filament_write_name": "1" if self.filament_name_var.get() else "0",
            "ntag_purchase_write_name": "1" if self.purchase_name_var.get() else "0",
            "ntag_url_write_name": "1" if self.url_name_var.get() else "0",
            "ntag_fields": self._serialize_type2_fields(),
            "timeout_startup": self.timeout_vars["startup"].get(),
            "timeout_idle": self.timeout_vars["idle"].get(),
            "timeout_command": self.timeout_vars["command"].get(),
            "timeout_operation": self.timeout_vars["operation"].get(),
        }
        key_map = {
            "source_dump_size": "mfc_source_dump_size",
            "source_key_size": "mfc_source_key_size",
            "source_bcc": "mfc_source_bcc",
            "source_trailer_keys": "mfc_source_trailer_keys",
            "source_access_bits": "mfc_source_access_bits",
            "source_filename_uid": "mfc_source_filename_uid",
            "client_firmware": "mfc_client_firmware",
            "tag_type": "mfc_tag_type",
            "magic_type": "mfc_magic_type",
            "default_keys": "mfc_default_keys",
            "backup": "mfc_backup",
            "target_stability": "mfc_target_stability",
            "verify_dump": "mfc_verify_dump",
            "verify_uid": "mfc_verify_uid",
        }
        for key, setting in key_map.items():
            values[setting] = "1" if self.mfc_option_vars[key].get() else "0"
        for key, var in self.ntag_option_vars.items():
            values[f"ntag_{key}"] = "1" if var.get() else "0"
        for key, var in self.erase_option_vars.items():
            values[f"erase_{key}"] = "1" if var.get() else "0"
        return values

    def _save_current_settings(self, *, show_error: bool = False) -> bool:
        """Persist settings atomically and report failures instead of hiding them."""

        try:
            save_settings(self._current_settings_values())
        except OSError as exc:
            LOGGER.exception("Failed to save application settings")
            message = self.t("settings.save_failed", error=str(exc))
            if hasattr(self, "settings_status_var"):
                self.settings_status_var.set(message)
            if show_error and hasattr(self, "dialogs"):
                self.dialogs.error(self.t("settings.save_failed_title"), message)
            return False
        return True

