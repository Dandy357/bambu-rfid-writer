from __future__ import annotations

from collections.abc import Callable

from ..i18n import Translator, normalize_locale
from ..domain import CheckItem, CheckState, CommandResult, TagInfo
from ..pm3_parsing import enrich_mfu_info
from ..pm3 import ProxmarkRunner


ProgressCallback = Callable[[str], None]
KNOWN_WRITE_PROFILES = frozenset({"ntag213", "ntag215", "ntag216"})


class Type2DiagnosticInspector:
    """Inspect NFC Type 2 identity, protection state, and originality data."""

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
        progress(self.t("diag.ntag_progress"))
        result = None
        if not info_already_read:
            result = runner.run("hf mfu info")
            commands.append(result)
            enrich_mfu_info(tag, result.output, self.locale)
        if result is not None and result.timed_out:
            tag.future_write_ready = False
            tag.readiness_detail = self.t("diag.ntag_timeout")
            checks.append(
                CheckItem(
                    self.t("diag.ntag_check"),
                    CheckState.ERROR,
                    tag.readiness_detail,
                )
            )
            return

        extra_output: list[str] = []
        for page in (tag.dynamic_lock_page, tag.config_page):
            if page is None:
                continue
            page_result = runner.read_mfu_page(page)
            commands.append(page_result)
            if page_result.timed_out or page_result.returncode != 0:
                tag.future_write_ready = False
                tag.readiness_detail = self.t("diag.ntag_timeout")
                checks.append(
                    CheckItem(
                        self.t("diag.ntag_check"),
                        CheckState.ERROR,
                        tag.readiness_detail,
                    )
                )
                return
            extra_output.append(page_result.output)
        if extra_output:
            enrich_mfu_info(
                tag, "\n".join([result.output, *extra_output]), self.locale
            )
        self.assess(tag, checks)

    def assess(self, tag: TagInfo, checks: list[CheckItem]) -> None:
        """Convert parsed Type 2 metadata into user-facing diagnostic checks."""
        if tag.type2_profile not in KNOWN_WRITE_PROFILES:
            tag.future_write_ready = False
            tag.readiness_detail = self.t("diag.type2_layout_unknown")
            checks.append(
                CheckItem(
                    self.t("diag.ntag_supported"),
                    CheckState.WARNING,
                    tag.readiness_detail,
                )
            )
            return

        checks.append(
            CheckItem(
                self.t("diag.ntag_supported"),
                CheckState.OK,
                self.t(
                    "diag.type2_profile_confirmed",
                    profile=tag.display_type,
                    capacity=tag.ndef_capacity or 0,
                ),
            )
        )
        self._add_originality_check(tag, checks)
        self._add_protection_check(tag, checks)

    def _add_originality_check(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        if tag.originality_verified is True:
            state = CheckState.OK
            detail = self.t("diag.originality_ok")
        elif tag.originality_verified is False:
            state = CheckState.WARNING
            all_zero = tag.originality_signature == "0" * 64
            detail = self.t(
                "diag.originality_zero"
                if all_zero
                else "diag.originality_failed"
            )
        else:
            state = CheckState.INFO
            detail = self.t("diag.originality_unknown")
        checks.append(CheckItem(self.t("diag.originality"), state, detail))

    def _add_protection_check(
        self, tag: TagInfo, checks: list[CheckItem]
    ) -> None:
        if tag.future_write_ready is True:
            state = CheckState.OK
            detail = tag.readiness_detail or self.t("diag.ntag_ready_default")
        elif tag.future_write_ready is False:
            state = CheckState.ERROR
            detail = tag.readiness_detail or self.t("diag.ntag_not_writable")
        else:
            state = CheckState.ERROR
            detail = tag.readiness_detail or self.t("diag.ntag_unknown")
        checks.append(CheckItem(self.t("diag.protection"), state, detail))
