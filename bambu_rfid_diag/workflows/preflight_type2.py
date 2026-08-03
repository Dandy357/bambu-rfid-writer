from __future__ import annotations

from ..domain import CheckItem, CheckState, HardwareInfo, TagInfo
from ..pm3_parsing import enrich_mfu_info, parse_hardware, parse_iso14a


def run_type2_preflight(workflow, runner, options, report, progress):
    """Identify a Type 2 tag and evaluate profile-selected safety checks."""
    # Profile identification is a technical requirement. Capacity and protected
    # pages cannot be constructed safely without these two commands.
    atoms: list[str] = ["hf 14a info", "hf mfu info"]
    firmware_cached = workflow.firmware_cached(
        options.profile, options.client_firmware
    )
    if options.client_firmware and not firmware_cached:
        atoms.insert(0, "hw version")

    hardware = HardwareInfo()
    tag = TagInfo()
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
        return hardware, tag, False

    hardware = parse_hardware(result.output)
    tag = parse_iso14a(result.output, workflow.locale)
    enrich_mfu_info(tag, result.output, workflow.locale)

    extra_output: list[str] = []
    if (
        options.dynamic_lock
        and tag.dynamic_lock is None
        and tag.dynamic_lock_page is not None
    ):
        page_result = runner.read_mfu_page(tag.dynamic_lock_page)
        report.commands.append(page_result)
        if workflow.command_succeeded(page_result):
            extra_output.append(page_result.output)
        else:
            workflow.add_check(
                report,
                CheckItem(
                    workflow.t("writer.dynamic_lock_check"),
                    CheckState.ERROR,
                    workflow.t("writer.preflight_command_failed"),
                    blocking=True,
                ),
            )
    if options.auth0 and tag.auth0 is None and tag.config_page is not None:
        page_result = runner.read_mfu_page(tag.config_page)
        report.commands.append(page_result)
        if workflow.command_succeeded(page_result):
            extra_output.append(page_result.output)
        else:
            workflow.add_check(
                report,
                CheckItem(
                    workflow.t("writer.auth0_check"),
                    CheckState.ERROR,
                    workflow.t("writer.preflight_command_failed"),
                    blocking=True,
                ),
            )
    if extra_output:
        enrich_mfu_info(
            tag, "\n".join([result.output, *extra_output]), workflow.locale
        )

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
        passed = tag.type2_profile in {"ntag213", "ntag215", "ntag216"}
        detail = (
            workflow.t(
                "writer.type2_profile_confirmed",
                profile=tag.display_type,
                capacity=tag.ndef_capacity or 0,
            )
            if passed
            else workflow.t("writer.type2_profile_not_supported")
        )
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("diag.ntag_supported"),
                CheckState.OK if passed else CheckState.ERROR,
                detail,
                blocking=not passed,
            ),
        )

    if options.static_lock:
        passed = tag.static_lock == "00 00"
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("writer.static_lock_check"),
                CheckState.OK if passed else CheckState.ERROR,
                workflow.t("writer.lock_ok")
                if passed
                else workflow.t(
                    "writer.lock_bad", value=tag.static_lock or "?"
                ),
                blocking=not passed,
            ),
        )
    if options.dynamic_lock:
        passed = tag.dynamic_lock == "00 00 00"
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("writer.dynamic_lock_check"),
                CheckState.OK if passed else CheckState.ERROR,
                workflow.t("writer.lock_ok")
                if passed
                else workflow.t(
                    "writer.lock_bad", value=tag.dynamic_lock or "?"
                ),
                blocking=not passed,
            ),
        )
    if options.auth0:
        passed = tag.auth0 == "FF"
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("writer.auth0_check"),
                CheckState.OK if passed else CheckState.ERROR,
                workflow.t("writer.auth0_ok")
                if passed
                else workflow.t("writer.auth0_bad", value=tag.auth0 or "?"),
                blocking=not passed,
            ),
        )
    if options.ecc_signature:
        if tag.originality_verified is True:
            state = CheckState.OK
            detail = workflow.t("diag.originality_ok")
        elif tag.originality_verified is False:
            state = CheckState.WARNING
            detail = workflow.t("writer.originality_warning")
        else:
            state = CheckState.INDETERMINATE
            detail = workflow.t("writer.originality_unknown")
        workflow.add_check(
            report,
            CheckItem(
                workflow.t("diag.originality"),
                state,
                detail,
                blocking=False,
            ),
        )

    report.target_uid_before = tag.uid
    ready = not any(item.blocking for item in report.checks)
    return hardware, tag, ready
