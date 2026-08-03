from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ..domain import CheckState, DiagnosticReport, OverallState
from ..i18n import Translator, normalize_locale
from ..infrastructure.paths import diagnostic_log_directory
from ..version import APP_NAME, APP_VERSION


STATE_KEYS = {
    CheckState.OK: "state.ok",
    CheckState.WARNING: "state.warning",
    CheckState.ERROR: "state.error",
    CheckState.INFO: "state.info",
    CheckState.SKIPPED: "state.skipped",
    CheckState.UNSUPPORTED: "state.unsupported",
    CheckState.INDETERMINATE: "state.indeterminate",
}

OVERALL_KEYS = {
    OverallState.READY: "overall.ready",
    OverallState.CAUTION: "overall.caution",
    OverallState.BLOCKED: "overall.blocked",
    OverallState.NO_TAG: "overall.no_tag",
    OverallState.ERROR: "overall.error",
}


def state_label(state: CheckState, locale: str = "en") -> str:
    """Return the localized label for one check state."""
    return Translator(locale).t(STATE_KEYS[state])


def overall_label(state: OverallState, locale: str = "en") -> str:
    """Return the localized label for one diagnostic overall state."""
    return Translator(locale).t(OVERALL_KEYS[state])


def format_report(report: DiagnosticReport, locale: str | None = None) -> str:
    """Render one deterministic localized diagnostic text report."""
    language = normalize_locale(locale or report.locale)
    t = Translator(language).t
    hardware = report.hardware
    tag = report.tag
    unknown = t("common.unknown")
    lines = [
        f"{APP_NAME} v{APP_VERSION}",
        "=" * 72,
        t("report.mode_1"),
        t("report.mode_2"),
        "",
        f"{t('report.start')}: {report.started_at_iso}",
        f"{t('report.end')}:   {report.finished_at_iso}",
        f"{t('report.bundle')}: {report.bundle_root}",
        f"{t('report.requested_port')}: "
        f"{report.requested_port or t('report.auto_detection')}",
        f"{t('report.pm3_sessions')}: {report.pm3_sessions}",
        "",
        f"{t('report.overall')}: "
        f"{overall_label(report.overall_state, language)}",
        report.summary,
        "",
        t("report.checks"),
        "-" * 72,
    ]
    for item in report.checks:
        lines.append(
            f"[{state_label(item.state, language)}] {item.name}: {item.detail}"
        )

    lines.extend(
        [
            "",
            t("report.device"),
            "-" * 72,
            f"{t('report.port')}: {hardware.port or unknown}",
            f"{t('report.communication')}: {hardware.communication or unknown}",
            f"{t('report.mcu')}: {hardware.mcu or unknown}",
            f"{t('report.memory')}: {hardware.memory or unknown}",
            f"{t('report.target')}: {hardware.target or unknown}",
            f"{t('report.client')}: {hardware.client_version or unknown}",
            f"{t('report.bootrom')}: {hardware.bootrom_version or unknown}",
            f"{t('report.os')}: {hardware.os_version or unknown}",
            f"{t('report.version_match')}: "
            f"{bool_label(hardware.version_match, language)}",
            "",
            t("report.tag"),
            "-" * 72,
            f"{t('report.present')}: "
            f"{t('common.yes') if tag.present else t('common.no')}",
            f"{t('report.type')}: {tag.display_type}",
            f"{t('report.family')}: {tag.family}",
            f"{t('report.uid')}: {tag.uid or unknown}",
            f"{t('report.atqa')}: {tag.atqa or unknown}",
            f"{t('report.sak')}: {tag.sak or unknown}",
            f"{t('report.magic')}: {tag.magic_kind or unknown}",
            f"{t('report.fingerprint')}: {tag.fingerprint or unknown}",
            f"{t('report.prng')}: {tag.prng or unknown}",
            f"{t('report.default_keys')}: "
            f"{bool_label(tag.default_keys, language)}",
            f"{t('report.sectors')}: {tag.default_key_sectors_seen}/16",
            f"{t('report.auth0')}: {tag.auth0 or unknown}",
            f"{t('report.static_lock')}: {tag.static_lock or unknown}",
            f"{t('report.dynamic_lock')}: {tag.dynamic_lock or unknown}",
            f"{t('report.originality_signature')}: "
            f"{tag.originality_signature or unknown}",
            f"{t('report.originality_verified')}: "
            f"{bool_label(tag.originality_verified, language)}",
            f"{t('report.write_readiness')}: "
            f"{bool_label(tag.future_write_ready, language)}",
            f"{t('report.assessment')}: "
            f"{tag.readiness_detail or t('report.no_assessment')}",
            "",
            t("report.raw_output"),
            "=" * 72,
        ]
    )

    for index, command in enumerate(report.commands, start=1):
        lines.extend(
            [
                "",
                f"{t('report.command', index=index)}: {command.command}",
                t(
                    "report.return",
                    code=command.returncode,
                    duration=command.duration_seconds,
                    timeout=(
                        t("common.yes")
                        if command.timed_out
                        else t("common.no")
                    ),
                ),
                *(
                    [
                        t(
                            "report.timeout_reason",
                            reason=t(
                                f"timeout.reason_{command.timeout_reason}"
                            ),
                        )
                    ]
                    if command.timeout_reason
                    else []
                ),
                "-" * 72,
                command.output or t("report.no_client_output"),
            ]
        )
    lines.append("")
    return "\n".join(lines)


def bool_label(value: bool | None, locale: str = "en") -> str:
    t = Translator(locale).t
    if value is True:
        return t("common.yes")
    if value is False:
        return t("common.no")
    return t("common.unknown")


def save_report(report: DiagnosticReport, locale: str | None = None) -> Path:
    """Persist one diagnostic report and update its path."""
    if locale is not None:
        report.locale = normalize_locale(locale)
    directory = diagnostic_log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    uid = (report.tag.uid or "no_tag").replace(" ", "")
    path = directory / f"diagnostic_{timestamp}_{uid}.txt"
    path.write_text(format_report(report), encoding="utf-8-sig")
    report.report_path = path
    return path


def report_as_dict(report: DiagnosticReport) -> dict:
    """Return a JSON-ready representation used by tests and integrations."""
    result = asdict(report)
    result["bundle_root"] = str(report.bundle_root)
    result["report_path"] = (
        str(report.report_path) if report.report_path else None
    )
    result["overall_state"] = report.overall_state.value
    for item in result["checks"]:
        state = item["state"]
        item["state"] = state.value if hasattr(state, "value") else state
    return result
