from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..domain.write_reports import WriteReport
from ..i18n import Translator, normalize_locale
from ..version import APP_NAME, APP_VERSION
from ..infrastructure.paths import app_data_directory
from .diagnostic_report import state_label


def safe_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def backup_directory(data_root: Path | None = None) -> Path:
    return (data_root or app_data_directory()) / "backups"


def write_log_directory(data_root: Path | None = None) -> Path:
    return (data_root or app_data_directory()) / "logs"


def verification_label(value: bool | None, locale: str) -> str:
    t = Translator(locale).t
    if value is True:
        return t("common.yes")
    if value is False:
        return t("common.no")
    return t("common.unknown")


def format_write_report(report: WriteReport, locale: str | None = None) -> str:
    """Render a deterministic localized text report."""
    language = normalize_locale(locale or report.locale)
    t = Translator(language).t
    result_label = (
        t("report.no_change")
        if report.no_change
        else t("report.success")
        if report.success
        else t("report.failure")
    )
    target_classification = report.target_classification or t("common.unknown")
    authentication_source = report.authentication_source or t("common.not_specified")
    lines = [
        f"{APP_NAME} v{APP_VERSION}",
        "=" * 72,
        f"{t('report.operation')}: {report.operation}",
        f"{t('report.start')}: {report.started_at_iso}",
        f"{t('report.end')}:   {report.finished_at_iso or t('common.not_finished')}",
        f"{t('report.result')}: {result_label}",
        f"{t('report.verified')}: {verification_label(report.verified, language)}",
        f"{t('report.pm3_sessions')}: {report.pm3_sessions}",
        f"{t('report.profile')}: {report.profile or t('common.not_specified')}",
        f"{t('report.method')}: {report.method or t('common.not_specified')}",
        f"{t('report.target_classification')}: {target_classification}",
        f"{t('report.authentication_source')}: {authentication_source}",
        report.summary,
        "",
        f"{t('report.source')}: {report.source_description or t('common.not_specified')}",
        f"{t('report.source_uid')}: {report.source_uid or t('common.not_specified')}",
        f"{t('report.target_uid_before')}: {report.target_uid_before or t('common.unknown')}",
        f"{t('report.target_uid_after')}:   {report.target_uid_after or t('common.unknown')}",
        f"{t('report.backup')}: {report.backup_path or t('common.not_created')}",
        "",
        t("report.checks"),
        "-" * 72,
    ]
    for check in report.checks:
        lines.append(f"[{state_label(check.state, language)}] {check.name}: {check.detail}")

    lines.extend(["", t("report.raw_output"), "=" * 72])
    for index, command in enumerate(report.commands, start=1):
        lines.extend(
            [
                "",
                f"{t('report.command', index=index)}: {command.command}",
                t(
                    "report.return",
                    code=command.returncode,
                    duration=command.duration_seconds,
                    timeout=t("common.yes") if command.timed_out else t("common.no"),
                ),
                *(
                    [
                        t(
                            "report.timeout_reason",
                            reason=t(f"timeout.reason_{command.timeout_reason}"),
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


def save_write_report(
    report: WriteReport, *, data_root: Path | None = None
) -> Path:
    """Persist a report using its stable operation identifier."""
    directory = write_log_directory(data_root)
    directory.mkdir(parents=True, exist_ok=True)
    uid = (report.target_uid_before or "no_uid").replace(" ", "")
    path = directory / (
        f"write_{report.operation_kind.value}_{safe_timestamp()}_{uid}.txt"
    )
    path.write_text(format_write_report(report), encoding="utf-8-sig")
    report.report_path = path
    return path
