from __future__ import annotations

import queue
import threading
import traceback
from dataclasses import replace
import tkinter as tk
from tkinter import END
from tkinter import ttk

from ..diagnostics import DiagnosticService
from ..ndef_reader import NdefReadService
from ..domain.operation_events import UiEvent, UiEventKind
from ..nfc_type2 import Type2Field
from ..options import (
    ERASE_SCOPE_NDEF,
    ERASE_SCOPE_USER,
    MfcWriteOptions,
    PROFILE_CUSTOM,
    TimeoutOptions,
    Type2EraseOptions,
    Type2WriteOptions,
)
from ..pm3 import BundleValidationError, resolve_bundle, validate_port
from ..presentation.diagnostic_report import save_report
from ..sources import MfcSource
from ..writer import WriterService
from .constants import MODE_CUID, MODE_TYPE2


class OperationControllerMixin:
    """Presentation behavior grouped by one GUI responsibility."""

    def _bundle_and_port(self) -> tuple[str, str | None] | None:
        bundle = self.bundle_var.get().strip()
        if not bundle:
            self.dialogs.error(
                self.t("app.settings_required_title"),
                self.t("app.settings_required"),
            )
            return None
        try:
            layout = resolve_bundle(bundle, self.locale)
            port = validate_port(self.port_var.get(), self.locale)
        except (BundleValidationError, ValueError) as exc:
            self.dialogs.error(self.t("app.invalid_settings_title"), str(exc))
            return None
        self.bundle_var.set(str(layout.root))
        return str(layout.root), port

    def _all_action_buttons(self) -> list[ttk.Button]:
        buttons = [
            self.bambu_write_button,
            self.cuid_check_button,
            self.ntag_write_button,
            self.ntag_check_button,
            self.ndef_read_button,
            self.ntag_erase_button,
            self.ntag_full_erase_button,
            self.library_load_button,
            self.library_refresh_button,
            *self.mode_switcher.buttons,
        ]
        buttons.extend(
            self.mode_views[mode]["diagnostic_button"]
            for mode in (MODE_CUID, MODE_TYPE2)
        )
        return buttons

    def _sync_cuid_quick_verify(self) -> None:
        value = self.cuid_verify_var.get()
        self.mfc_option_vars["verify_uid"].set(value)
        self.mfc_profile_var.set(PROFILE_CUSTOM)

    def _sync_type2_quick_verify(self) -> None:
        self.ntag_profile_var.set(PROFILE_CUSTOM)

    def _cancel_operation(self) -> None:
        if not self.busy:
            return
        self.cancel_event.set()
        self.progress_var.set(self.t("app.cancelling_operation"))
        self.activity_bar.set_cancelling()
        self.cancel_button.configure(state="disabled")

    def _prepare_busy(
        self, mode: str, text: str, *, reset_report: bool = True
    ) -> bool:
        if not self._save_current_settings(show_error=True):
            return False
        self.busy = True
        self.busy_mode = mode
        self.cancel_event.clear()
        self.cancel_button.configure(state="normal")
        for button in self._all_action_buttons():
            button.configure(state="disabled")
        view = self.mode_views[mode]
        if reset_report:
            view["open_button"].configure(state="disabled")
        self.activity_bar.start(mode)
        self.progress_var.set(text)
        if reset_report:
            view["result_var"].set(self.t("app.operation_running"))
            self.report_states[mode] = {"text": "", "path": None}
            view["path_var"].set("")
            view["log_text"].delete("1.0", END)
            for item in view["tree"].get_children():
                view["tree"].delete(item)
        return True

    def _start_bambu_write(self) -> None:
        if self.busy or not self._validate_source(True):
            return
        connection = self._bundle_and_port()
        if connection is None:
            return
        try:
            timeouts = self._current_timeouts()
        except ValueError as exc:
            self.dialogs.error(self.t("app.invalid_settings_title"), str(exc))
            return
        source = self.loaded_source
        if source is None:
            self.dialogs.error(
                self.t("app.invalid_source_title"),
                self.t("app.source_prompt"),
            )
            return
        options = self._current_mfc_options()
        confirmed = self.dialogs.confirm(
            self.t("app.confirm_bambu_title"),
            self.t(
                "app.confirm_bambu_v4",
                uid=source.uid_hex or self.t("common.unknown"),
                dump=source.dump_path.name,
                profile=self.t(f"settings.profile_{options.profile}"),
                backup=self.t("common.yes") if options.backup else self.t("common.no"),
                verify=(
                    self.t("common.yes")
                    if options.verify_dump or options.verify_uid
                    else self.t("common.no")
                ),
            ),
            accent="cuid",
        )
        if not confirmed:
            return
        bundle, port = connection
        locale = self.locale
        library_root = self.material_library_var.get().strip() or None
        if not self._prepare_busy(MODE_CUID, self.t("app.start_bambu")):
            return
        threading.Thread(
            target=self._bambu_worker,
            args=(bundle, source, port, options, timeouts, locale, library_root),
            daemon=True,
        ).start()

    def _bambu_worker(
        self,
        bundle: str,
        source: MfcSource,
        port: str | None,
        options: MfcWriteOptions,
        timeouts: TimeoutOptions,
        locale: str,
        library_root: str | None,
    ) -> None:
        try:
            report = WriterService(
                locale=locale,
                timeouts=timeouts,
                cancel_event=self.cancel_event,
                on_event=lambda event, payload: self.events.put(
                    UiEvent.live(MODE_CUID, event, payload)
                ),
            ).write_bambu(
                bundle,
                source,
                port,
                acknowledged_cuid_risk=True,
                options=options,
                library_root=library_root,
            )
            self.events.put(UiEvent.write_done(MODE_CUID, report))
        except Exception as exc:
            self.events.put(UiEvent.fatal(MODE_CUID, str(exc), traceback.format_exc()))

    def _start_type2_write(self) -> None:
        if self.busy:
            return
        connection = self._bundle_and_port()
        if connection is None:
            return
        try:
            timeouts = self._current_timeouts()
        except ValueError as exc:
            self.dialogs.error(self.t("app.invalid_settings_title"), str(exc))
            return
        tlv = self._preview_ndef()
        if tlv is None:
            return
        fields = self._collect_type2_fields()
        options = self._current_type2_options()
        confirmed = self.dialogs.confirm(
            self.t("app.confirm_ntag_title"),
            self.t(
                "app.confirm_ntag_v4", fields=len(fields), bytes=len(tlv),
                profile=self.t(f"settings.profile_{options.profile}"),
                method=self.t(f"settings.method_{options.method}"),
                backup=self.t("common.yes") if options.backup else self.t("common.no"),
                verify=self.t("common.yes") if options.final_verify else self.t("common.no"),
            ),
            accent="type2",
        )
        if not confirmed:
            return
        bundle, port = connection
        locale = self.locale
        if not self._prepare_busy(MODE_TYPE2, self.t("app.start_ntag")):
            return
        threading.Thread(
            target=self._type2_write_worker,
            args=(bundle, port, fields, options, timeouts, locale),
            daemon=True,
        ).start()

    def _type2_write_worker(
        self,
        bundle: str,
        port: str | None,
        fields: list[Type2Field],
        options: Type2WriteOptions,
        timeouts: TimeoutOptions,
        locale: str,
    ) -> None:
        try:
            report = WriterService(
                locale=locale,
                timeouts=timeouts,
                cancel_event=self.cancel_event,
                on_event=lambda event, payload: self.events.put(
                    UiEvent.live(MODE_TYPE2, event, payload)
                ),
            ).write_type2(
                bundle,
                port,
                fields=fields,
                options=options,
            )
            self.events.put(UiEvent.write_done(MODE_TYPE2, report))
        except Exception as exc:
            self.events.put(UiEvent.fatal(MODE_TYPE2, str(exc), traceback.format_exc()))

    def _start_type2_erase(self, scope: str = ERASE_SCOPE_NDEF) -> None:
        if self.busy:
            return
        connection = self._bundle_and_port()
        if connection is None:
            return
        try:
            timeouts = self._current_timeouts()
        except ValueError as exc:
            self.dialogs.error(self.t("app.invalid_settings_title"), str(exc))
            return
        options = replace(self._current_erase_options(), scope=scope)
        full_user_erase = scope == ERASE_SCOPE_USER
        confirmed = self.dialogs.confirm(
            self.t(
                "app.confirm_zero_title" if full_user_erase
                else "app.confirm_erase_title"
            ),
            self.t(
                "app.confirm_zero_user" if full_user_erase
                else "app.confirm_erase_v4",
                profile=self.t(f"settings.profile_{options.profile}"),
                method=self.t(f"settings.method_{options.method}"),
                backup=self.t("common.yes") if options.backup else self.t("common.no"),
                verify=self.t("common.yes") if options.final_verify else self.t("common.no"),
            ),
            accent="type2",
            destructive=full_user_erase,
        )
        if not confirmed:
            return
        bundle, port = connection
        locale = self.locale
        if not self._prepare_busy(
            MODE_TYPE2,
            self.t("app.start_zero_user" if full_user_erase else "app.start_erase"),
        ):
            return
        threading.Thread(
            target=self._type2_erase_worker,
            args=(bundle, port, options, timeouts, locale),
            daemon=True,
        ).start()

    def _type2_erase_worker(
        self,
        bundle: str,
        port: str | None,
        options: Type2EraseOptions,
        timeouts: TimeoutOptions,
        locale: str,
    ) -> None:
        try:
            report = WriterService(
                locale=locale,
                timeouts=timeouts,
                cancel_event=self.cancel_event,
                on_event=lambda event, payload: self.events.put(
                    UiEvent.live(MODE_TYPE2, event, payload)
                ),
            ).erase_type2(
                bundle,
                port,
                options=options,
            )
            self.events.put(UiEvent.write_done(MODE_TYPE2, report))
        except Exception as exc:
            self.events.put(UiEvent.fatal(MODE_TYPE2, str(exc), traceback.format_exc()))

    def _start_ndef_read(self) -> None:
        if self.busy:
            return
        connection = self._bundle_and_port()
        if connection is None:
            return
        try:
            timeouts = self._current_timeouts()
        except ValueError as exc:
            self.dialogs.error(self.t("app.invalid_settings_title"), str(exc))
            return
        bundle, port = connection
        locale = self.locale
        if not self._prepare_busy(
            MODE_TYPE2, self.t("app.start_read_ndef"), reset_report=False
        ):
            return
        threading.Thread(
            target=self._ndef_read_worker,
            args=(bundle, port, timeouts, locale),
            daemon=True,
        ).start()

    def _ndef_read_worker(
        self,
        bundle: str,
        port: str | None,
        timeouts: TimeoutOptions,
        locale: str,
    ) -> None:
        try:
            result = NdefReadService(
                locale=locale,
                timeouts=timeouts,
                cancel_event=self.cancel_event,
                on_event=lambda event, payload: self.events.put(
                    UiEvent.live(MODE_TYPE2, event, payload)
                ),
            ).read(
                bundle,
                port,
                on_progress=lambda message: self.events.put(UiEvent.progress(message)),
            )
            self.events.put(UiEvent.ndef_read_done(result))
        except Exception as exc:
            self.events.put(
                UiEvent.fatal(MODE_TYPE2, str(exc), traceback.format_exc())
            )

    def _start_diagnostic(self, mode: str) -> None:
        if self.busy:
            return
        connection = self._bundle_and_port()
        if connection is None:
            return
        try:
            timeouts = self._current_timeouts()
        except ValueError as exc:
            self.dialogs.error(self.t("app.invalid_settings_title"), str(exc))
            return
        bundle, port = connection
        locale = self.locale
        if not self._prepare_busy(mode, self.t("app.start_diagnostic")):
            return
        threading.Thread(
            target=self._diagnostic_worker,
            args=(mode, bundle, port, timeouts, locale),
            daemon=True,
        ).start()

    def _diagnostic_worker(
        self,
        mode: str,
        bundle: str,
        port: str | None,
        timeouts: TimeoutOptions,
        locale: str,
    ) -> None:
        try:
            report = DiagnosticService(
                locale=locale,
                timeouts=timeouts,
                cancel_event=self.cancel_event,
                on_event=lambda event, payload: self.events.put(
                    UiEvent.live(mode, event, payload)
                ),
            ).run(
                bundle,
                port,
                on_progress=lambda message: self.events.put(UiEvent.progress(message)),
                expected_family="mfc1k" if mode == MODE_CUID else "type2",
            )
            save_report(report)
            self.events.put(UiEvent.diagnostic_done(mode, report))
        except Exception as exc:
            self.events.put(UiEvent.fatal(mode, str(exc), traceback.format_exc()))

    def _poll_events(self) -> None:
        self._poll_after_id = None
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind is UiEventKind.PROGRESS:
                    self.progress_var.set(str(event.payload))
                elif event.kind is UiEventKind.LIVE:
                    live_event, live_payload = event.payload
                    self._handle_live_event(str(event.mode), str(live_event), live_payload)
                elif event.kind is UiEventKind.WRITE_DONE:
                    self._show_write_report(str(event.mode), event.payload)
                elif event.kind is UiEventKind.DIAGNOSTIC_DONE:
                    self._show_diagnostic_report(str(event.mode), event.payload)
                elif event.kind is UiEventKind.NDEF_READ_DONE:
                    self._show_ndef_read_result(event.payload)
                elif event.kind is UiEventKind.FATAL:
                    self._show_fatal(
                        str(event.mode), str(event.payload), str(event.details or "")
                    )
        except queue.Empty:
            pass
        finally:
            try:
                if self.root.winfo_exists():
                    self._poll_after_id = self.root.after(100, self._poll_events)
            except tk.TclError:
                self._poll_after_id = None

    def _finish_busy(self) -> None:
        self.busy = False
        self.activity_bar.stop()
        self.cancel_button.configure(state="disabled")
        for button in self._all_action_buttons():
            button.configure(state="normal")

    def _on_close(self) -> None:
        if self.busy:
            self.dialogs.warning(
                self.t("app.operation_in_progress_title"),
                self.t("app.close_blocked"),
            )
            return
        if not self._save_current_settings(show_error=True):
            return
        self.callbacks.cancel_all()
        if self._poll_after_id is not None:
            try:
                self.root.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        self.root.destroy()
