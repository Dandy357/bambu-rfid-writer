from __future__ import annotations

from ..domain import CheckItem, CheckState, HardwareInfo, TagInfo
from ..options import MfcWriteOptions
from ..pm3_parsing import (
    DefaultKeyCheck,
    enrich_mifare_info,
    parse_default_key_details,
    parse_hardware,
    parse_iso14a,
)


def run_mifare_preflight(workflow, runner, options: MfcWriteOptions, report, progress):
    """Run the optional MIFARE checks required by one clone profile."""
    atoms: list[str] = []
    firmware_cached = workflow.firmware_cached(
        options.profile, options.client_firmware
    )
    if options.client_firmware and not firmware_cached:
        atoms.append("hw version")
    if options.tag_type or options.target_stability or options.verify_uid:
        atoms.append("hf 14a info")
    if options.magic_type:
        atoms.append("hf mf info")
    if options.default_keys:
        atoms.append("hf mf chk --1k -k FFFFFFFFFFFF --no-default")

    hardware = HardwareInfo()
    tag = TagInfo()
    key_details = DefaultKeyCheck(False, 0, 0, None)
    if not atoms:
        return hardware, tag, key_details, True

    progress(workflow.t("writer.preflight_single_session"))
    result = runner.run(workflow.unique_atoms(atoms))
    report.commands.append(result)
    if not workflow.command_succeeded(result):
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("writer.preflight"),
                CheckState.ERROR,
                workflow.t("writer.preflight_command_failed"),
                blocking=True,
            ),
        )
        return hardware, tag, key_details, False

    hardware = parse_hardware(result.output)
    tag = parse_iso14a(result.output, workflow.locale)
    enrich_mifare_info(tag, result.output, workflow.locale)
    key_details = parse_default_key_details(result.output)
    tag.default_keys = key_details.all_default
    tag.default_key_sectors_seen = key_details.sectors_seen

    if options.client_firmware:
        if firmware_cached:
            passed = True
            detail = workflow.t("writer.client_firmware_cached")
        else:
            passed = hardware.version_match is True
            detail = (
                workflow.t("diag.versions_ok")
                if passed
                else workflow.t("diag.versions_mismatch")
            )
            workflow.remember_firmware_match(options.profile, passed)
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("diag.client_firmware"),
                CheckState.OK if passed else CheckState.ERROR,
                detail,
                blocking=not passed,
            ),
        )

    if options.tag_type:
        passed = tag.family == "mfc1k"
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("diag.supported_type"),
                CheckState.OK if passed else CheckState.ERROR,
                workflow.t("writer.mfc_type_ok")
                if passed
                else workflow.t("writer.mfc_type_bad"),
                blocking=not passed,
            ),
        )

    if options.magic_type:
        passed = bool(
            tag.magic_kind
            and ("CUID" in tag.magic_kind or "Gen2" in tag.magic_kind)
        )
        programmed_candidate = (
            options.default_keys
            and key_details.complete
            and key_details.successful_keys == 0
        )
        if passed:
            state = CheckState.OK
            detail = workflow.t(
                "diag.magic_reported",
                magic=tag.magic_kind or workflow.t("common.unknown"),
            )
            blocking = False
        elif programmed_candidate:
            state = CheckState.INDETERMINATE
            detail = workflow.t("writer.magic_deferred_programmed")
            blocking = False
        else:
            state = CheckState.ERROR
            detail = workflow.t("diag.magic_not_confirmed")
            blocking = True
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("diag.magic_type"),
                state,
                detail,
                blocking=blocking,
            ),
        )

    if options.default_keys:
        if key_details.complete and key_details.all_default is True:
            state = CheckState.OK
            detail = workflow.t("diag.default_keys_ok")
            blocking = False
        elif key_details.complete and key_details.successful_keys == 0:
            state = CheckState.WARNING
            detail = workflow.t("writer.default_keys_none_programmed")
            blocking = False
        elif key_details.complete:
            state = CheckState.ERROR
            detail = workflow.t(
                "writer.default_keys_partial",
                successful=key_details.successful_keys,
            )
            blocking = True
        else:
            state = CheckState.ERROR
            detail = workflow.t(
                "writer.default_keys_incomplete",
                sectors=key_details.sectors_seen,
            )
            blocking = True
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("diag.default_keys"),
                state,
                detail,
                blocking=blocking,
            ),
        )

    report.target_uid_before = tag.uid
    ready = not any(item.blocking for item in report.checks)
    return hardware, tag, key_details, ready
