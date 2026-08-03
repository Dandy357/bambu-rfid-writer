from __future__ import annotations

from collections.abc import Callable

from ..i18n import Translator, normalize_locale
from ..domain import CheckItem, CheckState, CommandResult, TagInfo
from ..pm3_parsing import (
    enrich_mifare_info,
    parse_default_key_check,
)
from ..pm3 import ProxmarkRunner


ProgressCallback = Callable[[str], None]


class MifareDiagnosticInspector:
    """Perform read-only MIFARE Classic diagnostics and readiness assessment."""

    def __init__(self, locale: str = "en") -> None:
        self.locale = normalize_locale(locale)
        self.t = Translator(self.locale).t

    def run(
        self,
        runner: ProxmarkRunner,
        tag: TagInfo,
        checks: list[CheckItem],
        commands: list[CommandResult],
        progress: ProgressCallback,
        *,
        info_already_read: bool = False,
    ) -> None:
        progress(self.t("diag.mfc_progress"))
        command = "hf mf chk --1k -k FFFFFFFFFFFF --no-default"
        if not info_already_read:
            command = "hf mf info; " + command
        result = runner.run(command)
        commands.append(result)
        enrich_mifare_info(tag, result.output, self.locale)
        tag.default_keys, tag.default_key_sectors_seen = parse_default_key_check(
            result.output
        )

        if result.timed_out:
            tag.future_write_ready = False
            tag.readiness_detail = self.t("diag.mfc_timeout")
            checks.append(
                CheckItem(
                    self.t("diag.mfc_check"),
                    CheckState.ERROR,
                    tag.readiness_detail,
                )
            )
            return

        self._add_magic_check(tag, checks)
        self._add_default_key_check(tag, checks)
        self._assess_readiness(tag, checks)

    def _add_magic_check(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        if tag.magic_kind:
            state = (
                CheckState.OK
                if "CUID" in tag.magic_kind or "Gen2" in tag.magic_kind
                else CheckState.WARNING
            )
            checks.append(
                CheckItem(
                    self.t("diag.magic_type"),
                    state,
                    self.t("diag.magic_reported", magic=tag.magic_kind),
                )
            )
            return
        checks.append(
            CheckItem(
                self.t("diag.magic_type"),
                CheckState.ERROR,
                self.t("diag.magic_not_confirmed"),
            )
        )

    def _add_default_key_check(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        if tag.default_keys is True:
            state = CheckState.OK
            detail = self.t("diag.default_keys_ok")
        elif tag.default_keys is False:
            state = CheckState.ERROR
            detail = self.t("diag.default_keys_bad")
        else:
            state = CheckState.ERROR
            detail = self.t(
                "diag.default_keys_unknown",
                sectors=tag.default_key_sectors_seen,
            )
        checks.append(CheckItem(self.t("diag.default_keys"), state, detail))

    def _assess_readiness(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        correct_magic = bool(
            tag.magic_kind
            and ("CUID" in tag.magic_kind or "Gen2" in tag.magic_kind)
        )
        if correct_magic and tag.default_keys is True:
            tag.future_write_ready = True
            tag.readiness_detail = self.t("diag.bambu_ready")
            checks.append(
                CheckItem(
                    self.t("diag.bambu_readiness"),
                    CheckState.WARNING,
                    tag.readiness_detail,
                )
            )
            return
        tag.future_write_ready = False
        tag.readiness_detail = self.t("diag.bambu_blocked")
        checks.append(
            CheckItem(
                self.t("diag.bambu_readiness"),
                CheckState.ERROR,
                tag.readiness_detail,
            )
        )
