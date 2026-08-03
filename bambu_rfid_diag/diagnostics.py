from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .diagnostic import MifareDiagnosticInspector, Type2DiagnosticInspector
from .i18n import Translator, normalize_locale
from .domain import (
    CheckItem,
    CheckState,
    DiagnosticReport,
    HardwareInfo,
    OverallState,
    TagInfo,
)
from .pm3_parsing import (
    enrich_mfu_info,
    enrich_mifare_info,
    parse_hardware,
    parse_iso14a,
)
from .options import TimeoutOptions
from .pm3 import (
    OperationCancelledError,
    ProxmarkError,
    ProxmarkRunner,
    resolve_bundle,
    validate_port,
)


ProgressCallback = Callable[[str], None]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connection_failure_message(
    output: str, requested_port: str | None, locale: str = "en"
) -> tuple[str, str]:
    """Return a localized connection detail and concise failure summary."""
    t = Translator(locale).t
    invalid_port = re.search(
        r"ERROR:\s*invalid serial port\s+([^\s`]+)", output, flags=re.IGNORECASE
    )
    access_denied = re.search(
        r"(?:access is denied|access denied|permission denied)",
        output,
        flags=re.IGNORECASE,
    )
    if invalid_port or access_denied:
        port = (
            invalid_port.group(1).upper().rstrip(".")
            if invalid_port
            else (requested_port or t("diag.selected_port"))
        )
        detail = t("diag.port_open_detail", port=port)
        summary = t("diag.port_open_summary", port=port)
        return detail, summary

    return t("diag.connection_unconfirmed"), t("diag.connection_failed")


class DiagnosticService:
    """Orchestrate the read-only Proxmark3 diagnostic workflow."""

    def __init__(
        self,
        timeout_seconds: int = 60,
        locale: str = "en",
        *,
        timeouts: TimeoutOptions | None = None,
        cancel_event=None,
        on_event=None,
    ):
        self.timeout_seconds = timeout_seconds
        self.timeouts = timeouts or TimeoutOptions(
            startup_seconds=45,
            idle_seconds=max(90, timeout_seconds),
            command_seconds=max(120, timeout_seconds),
            operation_seconds=max(600, timeout_seconds * 4),
        )
        self.cancel_event = cancel_event
        self.on_event = on_event
        self.locale = normalize_locale(locale)
        self.tr = Translator(self.locale)
        self.t = self.tr.t
        self.mifare_inspector = MifareDiagnosticInspector(self.locale)
        self.type2_inspector = Type2DiagnosticInspector(self.locale)

    def run(
        self,
        bundle_root: str | Path,
        port: str | None = None,
        on_progress: ProgressCallback | None = None,
        *,
        expected_family: str | None = None,
    ) -> DiagnosticReport:
        progress = on_progress or (lambda _message: None)
        started = _now_iso()
        requested_port = validate_port(port, self.locale)

        progress(self.t("diag.check_bundle_progress"))
        layout = resolve_bundle(bundle_root, self.locale)
        runner = ProxmarkRunner(
            layout,
            requested_port,
            locale=self.locale,
            timeouts=self.timeouts,
            cancel_event=self.cancel_event,
            on_event=self.on_event,
        )
        checks = [
            CheckItem(
                self.t("diag.bundle_check"),
                CheckState.OK,
                self.t("diag.bundle_ok"),
            )
        ]
        commands = []
        hardware = HardwareInfo()
        tag = TagInfo()
        try:
            progress(self.t("diag.connect_progress"))
            runner.open()
            initial = runner.run("hw version; hf 14a info")
            commands.append(initial)
            hardware = parse_hardware(initial.output)
            tag = parse_iso14a(initial.output, self.locale)

            early = self._initial_failure_report(
                started=started,
                bundle_root=layout.root,
                requested_port=requested_port,
                initial=initial,
                hardware=hardware,
                tag=tag,
                checks=checks,
                commands=commands,
                sessions=runner.session_count,
            )
            if early is not None:
                return early

            self._append_connection_check(hardware, requested_port, checks)
            self._append_firmware_check(hardware, checks)

            if not tag.present:
                return self._no_tag_report(
                    started,
                    layout.root,
                    requested_port,
                    hardware,
                    tag,
                    checks,
                    commands,
                    runner.session_count,
                )

            self._append_tag_identity(tag, checks)
            self._inspect_tag(
                runner,
                tag,
                checks,
                commands,
                progress,
                expected_family=expected_family,
            )
            if hardware.version_match is False:
                tag.future_write_ready = False
                tag.readiness_detail = self.t("diag.version_blocks")

            overall, summary = self._overall(tag, hardware)
            return self._finish(
                started,
                layout.root,
                requested_port,
                overall,
                summary,
                hardware,
                tag,
                checks,
                commands,
                pm3_sessions=runner.session_count,
            )
        except OperationCancelledError:
            checks.append(
                CheckItem(
                    self.t("writer.operation_cancelled"),
                    CheckState.WARNING,
                    self.t("diag.cancelled_detail"),
                )
            )
            return self._finish(
                started,
                layout.root,
                requested_port,
                OverallState.ERROR,
                self.t("diag.cancelled_summary"),
                hardware,
                tag,
                checks,
                commands,
                pm3_sessions=runner.session_count,
            )
        except ProxmarkError as exc:
            checks.append(
                CheckItem(
                    self.t("diag.communication_check"),
                    CheckState.ERROR,
                    str(exc),
                )
            )
            return self._finish(
                started,
                layout.root,
                requested_port,
                OverallState.ERROR,
                str(exc),
                hardware,
                tag,
                checks,
                commands,
                pm3_sessions=runner.session_count,
            )
        finally:
            runner.close()

    def _initial_failure_report(
        self,
        *,
        started: str,
        bundle_root: Path,
        requested_port: str | None,
        initial,
        hardware: HardwareInfo,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list,
        sessions: int,
    ) -> DiagnosticReport | None:
        if initial.timed_out:
            checks.append(
                CheckItem(
                    self.t("diag.communication_check"),
                    CheckState.ERROR,
                    self.t("diag.timeout_detail"),
                )
            )
            return self._finish(
                started,
                bundle_root,
                requested_port,
                OverallState.ERROR,
                self.t("diag.timeout_summary"),
                hardware,
                tag,
                checks,
                commands,
                pm3_sessions=sessions,
            )
        if hardware.connected:
            return None

        detail, failure_summary = _connection_failure_message(
            initial.output, requested_port, self.locale
        )
        if initial.returncode != 0:
            detail += self.t("diag.return_code", code=initial.returncode)
        checks.append(
            CheckItem(
                self.t("diag.communication_check"),
                CheckState.ERROR,
                detail,
            )
        )
        return self._finish(
            started,
            bundle_root,
            requested_port,
            OverallState.ERROR,
            failure_summary,
            hardware,
            tag,
            checks,
            commands,
            pm3_sessions=sessions,
        )

    def _append_connection_check(
        self,
        hardware: HardwareInfo,
        requested_port: str | None,
        checks: list[CheckItem],
    ) -> None:
        if requested_port is None and hardware.port:
            detail = self.t("diag.communication_auto", port=hardware.port)
        elif hardware.port:
            detail = self.t("diag.communication_manual", port=hardware.port)
        else:
            detail = self.t("diag.communication_generic")
        checks.append(
            CheckItem(self.t("diag.communication_check"), CheckState.OK, detail)
        )

    def _append_firmware_check(
        self, hardware: HardwareInfo, checks: list[CheckItem]
    ) -> None:
        if hardware.version_match is True:
            state = CheckState.OK
            detail = self.t("diag.versions_ok")
        elif hardware.version_match is False:
            state = CheckState.ERROR
            detail = self.t("diag.versions_mismatch")
        else:
            state = CheckState.WARNING
            detail = self.t("diag.versions_unknown")
        checks.append(CheckItem(self.t("diag.client_firmware"), state, detail))

    def _no_tag_report(
        self,
        started: str,
        bundle_root: Path,
        requested_port: str | None,
        hardware: HardwareInfo,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list,
        sessions: int,
    ) -> DiagnosticReport:
        checks.append(
            CheckItem(
                self.t("diag.attached_tag"),
                CheckState.INFO,
                self.t("diag.no_tag_detail"),
            )
        )
        state = (
            OverallState.BLOCKED
            if hardware.version_match is False
            else OverallState.NO_TAG
        )
        return self._finish(
            started,
            bundle_root,
            requested_port,
            state,
            self.t("diag.no_tag_summary"),
            hardware,
            tag,
            checks,
            commands,
            pm3_sessions=sessions,
        )

    def _append_tag_identity(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        checks.append(
            CheckItem(
                self.t("diag.attached_tag"),
                CheckState.OK,
                self.t(
                    "diag.tag_found",
                    tag_type=tag.display_type,
                    uid=tag.uid or self.t("common.unknown"),
                    atqa=tag.atqa or "?",
                    sak=tag.sak or "?",
                ),
            )
        )

    def _inspect_tag(
        self,
        runner: ProxmarkRunner,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list,
        progress: ProgressCallback,
        *,
        expected_family: str | None = None,
    ) -> None:
        if expected_family == "mfc1k":
            self._inspect_expected_mifare(runner, tag, checks, commands, progress)
            return
        if expected_family == "type2":
            self._inspect_expected_type2(runner, tag, checks, commands, progress)
            return

        if tag.family == "mfc1k":
            self.mifare_inspector.run(runner, tag, checks, commands, progress)
            return
        if tag.family in {"ntag213", "ntag215", "ntag216", "type2"}:
            self.type2_inspector.run(runner, tag, checks, commands, progress)
            return

        progress(self.t("diag.unknown_type_progress"))
        probe = runner.run("hf mf info; hf mfu info")
        commands.append(probe)
        enrich_mifare_info(tag, probe.output, self.locale)
        enrich_mfu_info(tag, probe.output, self.locale)
        if tag.family == "mfc1k":
            self.mifare_inspector.run(
                runner,
                tag,
                checks,
                commands,
                progress,
                info_already_read=True,
            )
        elif tag.family in {"ntag213", "ntag215", "ntag216", "type2"}:
            self.type2_inspector.run(
                runner,
                tag,
                checks,
                commands,
                progress,
                info_already_read=True,
            )
        else:
            self._mark_unsupported(tag, checks)

    def _inspect_expected_mifare(
        self,
        runner: ProxmarkRunner,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list,
        progress: ProgressCallback,
    ) -> None:
        if tag.family == "mfc1k":
            self.mifare_inspector.run(runner, tag, checks, commands, progress)
            return
        if tag.family in {"ntag213", "ntag215", "ntag216", "type2"}:
            self._mark_wrong_target(tag, checks, "diag.expected_cuid")
            return
        progress(self.t("diag.mfc_progress"))
        probe = runner.run("hf mf info")
        commands.append(probe)
        enrich_mifare_info(tag, probe.output, self.locale)
        if tag.family == "mfc1k":
            self.mifare_inspector.run(
                runner, tag, checks, commands, progress, info_already_read=True
            )
        else:
            self._mark_wrong_target(tag, checks, "diag.expected_cuid")

    def _inspect_expected_type2(
        self,
        runner: ProxmarkRunner,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list,
        progress: ProgressCallback,
    ) -> None:
        if tag.family in {"ntag213", "ntag215", "ntag216", "type2"}:
            self.type2_inspector.run(runner, tag, checks, commands, progress)
            return
        if tag.family == "mfc1k":
            self._mark_wrong_target(tag, checks, "diag.expected_ndef")
            return
        progress(self.t("diag.ntag_progress"))
        probe = runner.run("hf mfu info")
        commands.append(probe)
        enrich_mfu_info(tag, probe.output, self.locale)
        if tag.family in {"ntag213", "ntag215", "ntag216", "type2"}:
            self.type2_inspector.run(
                runner,
                tag,
                checks,
                commands,
                progress,
                info_already_read=True,
            )
        else:
            self._mark_wrong_target(tag, checks, "diag.expected_ndef")

    def _mark_wrong_target(
        self, tag: TagInfo, checks: list[CheckItem], expected_key: str
    ) -> None:
        tag.future_write_ready = False
        tag.readiness_detail = self.t(
            "diag.wrong_target_detail",
            expected=self.t(expected_key),
            actual=tag.display_type,
        )
        checks.append(
            CheckItem(
                self.t("diag.selected_check"),
                CheckState.ERROR,
                tag.readiness_detail,
            )
        )

    def _mark_unsupported(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        tag.future_write_ready = False
        tag.readiness_detail = self.t("diag.type_unrecognized")
        checks.append(
            CheckItem(
                self.t("diag.supported_type"),
                CheckState.ERROR,
                self.t("diag.type_not_supported"),
            )
        )

    def _overall(self, tag: TagInfo, hardware: HardwareInfo) -> tuple[OverallState, str]:
        if hardware.version_match is False:
            return (
                OverallState.BLOCKED,
                self.t("diag.overall_version_blocked"),
            )
        if tag.future_write_ready is True and tag.family == "mfc1k":
            return (
                OverallState.CAUTION,
                self.t("diag.overall_mfc_caution"),
            )
        known_type2_profiles = {"ntag213", "ntag215", "ntag216"}
        if (
            tag.future_write_ready is True
            and tag.type2_profile in known_type2_profiles
        ):
            return (
                OverallState.READY,
                self.t("diag.overall_ntag_ready"),
            )
        return (
            OverallState.BLOCKED,
            tag.readiness_detail or self.t("diag.overall_blocked"),
        )

    def _finish(
        self,
        started: str,
        bundle_root: Path,
        requested_port: str | None,
        state: OverallState,
        summary: str,
        hardware: HardwareInfo,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list,
        pm3_sessions: int = 1,
    ) -> DiagnosticReport:
        return DiagnosticReport(
            started_at_iso=started,
            finished_at_iso=_now_iso(),
            bundle_root=bundle_root,
            requested_port=requested_port,
            overall_state=state,
            summary=summary,
            hardware=hardware,
            tag=tag,
            checks=checks,
            commands=commands,
            locale=self.locale,
            pm3_sessions=pm3_sessions,
        )
