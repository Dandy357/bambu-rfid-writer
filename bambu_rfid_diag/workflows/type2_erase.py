from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..domain.errors import WorkflowInvariantError
from ..domain.operation_events import OperationEventName
from ..domain.operations import OperationKind
from ..domain.write_reports import WriteReport
from ..infrastructure import OperationWorkspace
from ..domain import CheckItem, CheckState, TagInfo
from ..nfc_type2 import MFU_HEADER_SIZE, MfuDump, clear_ndef_tlv_area, parse_mfu_dump
from ..options import (
    ERASE_SCOPE_NDEF,
    ERASE_SCOPE_USER,
    Type2EraseOptions,
    TYPE2_METHOD_RESTORE,
)
from ..pm3 import OperationCancelledError, ProxmarkWriteRunner
from ..type2 import Type2Profile, profile_from_identifier
from .common import (
    ProgressCallback,
    WorkflowBase,
    command_ok,
    hex_uid,
    now_iso,
    read_exact_output,
)


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Type2ErasePlan:
    """Prepared memory range and target image for one erase operation."""

    profile: Type2Profile
    first_page: int
    last_page: int
    current_area: bytes
    target_area: bytes
    pages_to_write: list[int]
    baseline_data: bytes | None = None
    baseline_dump: MfuDump | None = None

    @property
    def page_count(self) -> int:
        return self.last_page - self.first_page + 1

    @property
    def changed_page_count(self) -> int:
        return len(self.pages_to_write)


class Type2EraseWorkflow(WorkflowBase):
    """Clear NDEF content or zero the known Type 2 user-memory area."""

    def run(
        self,
        bundle_root: str | Path,
        port: str | None,
        *,
        options: Type2EraseOptions | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WriteReport:
        options = options or Type2EraseOptions()
        report = self._create_report(options)
        progress = self._progress_callback(on_progress)
        workspace: OperationWorkspace | None = None

        self._emit(OperationEventName.OPERATION_STARTED, report)
        try:
            layout, runner = self._runner(bundle_root, port)
            workspace = self._create_workspace(layout.client_dir)

            with runner:
                report.pm3_sessions = runner.session_count
                _hardware, tag, ready = self._preflight_type2(
                    runner, options, report, progress
                )
                if not ready:
                    report.summary = self.t("writer.ntag_preflight_failed")
                    return self._finish(report)

                profile = self._resolve_profile(tag, report)
                if profile is None:
                    return self._finish(report)
                page_range = self._select_range(profile, options, report)
                if page_range is None:
                    return self._finish(report)
                first_page, last_page = page_range

                plan = self._prepare_plan(
                    runner=runner,
                    workspace=workspace,
                    tag=tag,
                    profile=profile,
                    first_page=first_page,
                    last_page=last_page,
                    options=options,
                    report=report,
                    progress=progress,
                )
                if plan is None:
                    return self._finish(report)
                if not self._execute_erase(
                    runner, workspace, plan, options, report, progress
                ):
                    return self._finish(report)
                if not self._verify_result(
                    runner, workspace, plan, options, report, progress
                ):
                    return self._finish(report)

                self._mark_success(options, report)
                return self._finish(report)
        except OperationCancelledError as exc:
            return self.finish_cancelled(report, exc)
        except Exception as exc:
            return self.finish_unexpected(report, exc, LOGGER)
        finally:
            if workspace is not None:
                workspace.cleanup()

    def _create_report(self, options: Type2EraseOptions) -> WriteReport:
        operation_kind = (
            OperationKind.TYPE2_NDEF_CLEAR
            if options.scope == ERASE_SCOPE_NDEF
            else OperationKind.TYPE2_USER_ZERO
        )
        return WriteReport(
            operation_kind=operation_kind,
            operation=self.t(
                "writer.ntag_erase_operation"
                if options.scope == ERASE_SCOPE_NDEF
                else "writer.type2_user_zero_operation"
            ),
            started_at_iso=now_iso(),
            source_description=self.t("writer.erase_source_generic"),
            locale=self.locale,
            profile=self.t(f"settings.profile_{options.profile}"),
            method=self.t(f"settings.method_{options.method}"),
        )

    @staticmethod
    def _create_workspace(client_directory: Path) -> OperationWorkspace:
        workspace = OperationWorkspace(client_directory)
        workspace.reserve_many(
            {
                "before": "type2_before_erase.bin",
                "verify": "type2_erase_verify.bin",
                "restore": "type2_erase_restore.bin",
            }
        )
        return workspace

    def _resolve_profile(
        self, tag: TagInfo, report: WriteReport
    ) -> Type2Profile | None:
        profile = profile_from_identifier(tag.type2_profile)
        if profile is not None:
            return profile
        self.add_check(
            report,
            CheckItem(
                self.t("writer.memory_profile"),
                CheckState.ERROR,
                self.t("writer.memory_profile_unknown"),
                blocking=True,
            ),
        )
        report.summary = self.t("writer.ntag_preflight_failed")
        return None

    def _select_range(
        self,
        profile: Type2Profile,
        options: Type2EraseOptions,
        report: WriteReport,
    ) -> tuple[int, int] | None:
        if options.scope == ERASE_SCOPE_USER:
            if profile.user_last_page is None:
                self.add_check(
                    report,
                    CheckItem(
                        self.t("writer.memory_profile"),
                        CheckState.ERROR,
                        self.t("writer.full_erase_unknown_profile"),
                        blocking=True,
                    ),
                )
                report.summary = self.t("writer.ntag_preflight_failed")
                return None
            first_page = profile.user_first_page
            last_page = profile.user_last_page
            report.source_description = self.t(
                "writer.erase_user_source_range",
                profile=profile.display_name,
                first=first_page,
                last=last_page,
            )
            return first_page, last_page

        first_page = profile.ndef_first_page
        last_page = profile.ndef_last_page
        report.source_description = self.t(
            "writer.erase_source_range",
            profile=profile.display_name,
            first=first_page,
            last=last_page,
        )
        return first_page, last_page

    def _prepare_plan(
        self,
        *,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        tag: TagInfo,
        profile: Type2Profile,
        first_page: int,
        last_page: int,
        options: Type2EraseOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> Type2ErasePlan | None:
        baseline = None
        if self._baseline_required(options):
            baseline = self._read_baseline(
                runner,
                workspace,
                tag,
                profile,
                first_page,
                last_page,
                options,
                report,
                progress,
            )
            if baseline is None:
                return None
        baseline_data, baseline_dump = baseline or (None, None)
        page_count = last_page - first_page + 1

        if options.scope == ERASE_SCOPE_NDEF:
            if baseline_dump is None:
                raise WorkflowInvariantError(
                    "Safe NDEF clearing requires a complete baseline dump"
                )
            current_area = bytes(
                baseline_dump.pages[first_page * 4 : (last_page + 1) * 4]
            )
            try:
                target_area, had_ndef = clear_ndef_tlv_area(
                    current_area, self.locale
                )
            except ValueError as exc:
                self.add_check(
                    report,
                    CheckItem(
                        self.t("writer.ndef_tlv_map"),
                        CheckState.ERROR,
                        str(exc),
                        blocking=True,
                    ),
                )
                report.summary = self.t("writer.erase_compare_failed")
                return None
            if not had_ndef:
                target_area = current_area
        else:
            current_area = (
                bytes(
                    baseline_dump.pages[
                        first_page * 4 : (last_page + 1) * 4
                    ]
                )
                if baseline_dump is not None
                else b"\xFF" * (page_count * 4)
            )
            target_area = b"\x00" * (page_count * 4)

        compare_pages = (
            options.scope == ERASE_SCOPE_NDEF
            or options.scan_nonzero_pages
        )
        pages_to_write = [
            page
            for page in range(first_page, last_page + 1)
            if not compare_pages
            or self._page_slice(current_area, first_page, page)
            != self._page_slice(target_area, first_page, page)
        ]
        return Type2ErasePlan(
            profile=profile,
            first_page=first_page,
            last_page=last_page,
            current_area=current_area,
            target_area=target_area,
            pages_to_write=pages_to_write,
            baseline_data=baseline_data,
            baseline_dump=baseline_dump,
        )

    @staticmethod
    def _baseline_required(options: Type2EraseOptions) -> bool:
        return bool(
            options.scope == ERASE_SCOPE_NDEF
            or options.backup
            or options.target_stability
            or options.scan_nonzero_pages
            or options.method == TYPE2_METHOD_RESTORE
            or (options.protected_verify and options.final_verify)
        )

    def _read_baseline(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        tag: TagInfo,
        profile: Type2Profile,
        first_page: int,
        last_page: int,
        options: Type2EraseOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> tuple[bytes, MfuDump] | None:
        progress(
            self.t(
                "writer.backup_progress_ntag"
                if options.backup
                else "writer.baseline_progress_ntag"
            )
        )
        result = runner.dump_mfu(workspace.names["before"])
        report.commands.append(result)
        if not self._validate_mfu_dump(result, workspace.paths["before"]):
            report.summary = self.t("writer.backup_failed_ntag")
            return None

        data = read_exact_output(workspace.paths["before"], self.locale)
        dump = parse_mfu_dump(data, self.locale)
        if dump.profile is not None and (
            dump.profile.identifier != profile.identifier
        ):
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.memory_profile"),
                    CheckState.ERROR,
                    self.t(
                        "writer.memory_profile_changed",
                        expected=profile.display_name,
                        actual=dump.profile.display_name,
                    ),
                    blocking=True,
                ),
            )
            report.summary = self.t("writer.ntag_preflight_failed")
            return None

        if not report.target_uid_before:
            report.target_uid_before = " ".join(
                f"{byte:02X}" for byte in dump.uid
            )
        if options.target_stability:
            expected = hex_uid(tag.uid)
            actual = dump.uid.hex().upper()
            passed = not expected or expected == actual
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.target_stability"),
                    CheckState.OK if passed else CheckState.ERROR,
                    self.t("writer.target_stable")
                    if passed
                    else self.t("writer.backup_uid_mismatch"),
                    blocking=not passed,
                ),
            )
            if not passed:
                report.summary = self.t("writer.backup_uid_mismatch")
                return None

        if options.backup:
            area = dump.pages[first_page * 4 : (last_page + 1) * 4]
            save_empty = options.profile == "thorough"
            if save_empty or any(area):
                report.backup_path = self._copy_persistent_backup(
                    workspace.paths["before"],
                    "ntag_before_erase",
                    dump.uid.hex().upper(),
                )
                self.add_check(
                    report,
                    CheckItem(
                        self.t("writer.backup_target"),
                        CheckState.OK,
                        self.t(
                            "writer.backup_saved",
                            bytes=len(data),
                            path=report.backup_path,
                        ),
                    ),
                )
            else:
                self.add_check(
                    report,
                    CheckItem(
                        self.t("writer.backup_target"),
                        CheckState.SKIPPED,
                        self.t("writer.backup_skipped_empty"),
                    ),
                )
        return data, dump

    def _execute_erase(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        plan: Type2ErasePlan,
        options: Type2EraseOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if plan.changed_page_count == 0:
            self.add_check(
                report,
                CheckItem(
                    self._operation_check_name(options),
                    CheckState.SKIPPED,
                    self.t(
                        "writer.erase_already_empty"
                        if options.scope == ERASE_SCOPE_NDEF
                        else "writer.user_area_already_zero",
                        pages=plan.page_count,
                    ),
                ),
            )
            return True

        if options.method == TYPE2_METHOD_RESTORE:
            if plan.baseline_data is None:
                raise WorkflowInvariantError(
                    "Type 2 restore erase requires a complete baseline dump"
                )
            image = bytearray(plan.baseline_data)
            start = MFU_HEADER_SIZE + plan.first_page * 4
            end = MFU_HEADER_SIZE + (plan.last_page + 1) * 4
            image[start:end] = plan.target_area
            workspace.paths["restore"].write_bytes(bytes(image))
            progress(
                self.t(
                    "writer.erase_pages_batch_progress",
                    pages=plan.changed_page_count,
                )
            )
            restore_result = runner.restore_mfu(workspace.names["restore"])
            self._validate_mfu_restore(restore_result)
            results = [restore_result]
        else:
            progress(
                self.t(
                    "writer.erase_pages_batch_progress",
                    pages=plan.changed_page_count,
                )
            )
            results = self._write_pages(
                runner,
                options.method,
                [
                    (
                        page,
                        self._page_slice(
                            plan.target_area, plan.first_page, page
                        ),
                    )
                    for page in plan.pages_to_write
                ],
                max_page=plan.last_page,
                progress=progress,
            )
        report.commands.extend(results)
        if all(command_ok(result) for result in results):
            return True
        report.summary = self.t("writer.erase_batch_failed")
        return False

    def _verify_result(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        plan: Type2ErasePlan,
        options: Type2EraseOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if not options.final_verify:
            return True
        progress(self.t("writer.erase_verify_progress"))
        result = runner.dump_mfu(workspace.names["verify"])
        report.commands.append(result)
        if not self._validate_mfu_dump(result, workspace.paths["verify"]):
            report.summary = self.t("writer.erase_verify_failed")
            return False

        dump = parse_mfu_dump(
            read_exact_output(workspace.paths["verify"], self.locale),
            self.locale,
        )
        report.target_uid_after = dump.uid.hex().upper()
        area = bytes(
            dump.pages[plan.first_page * 4 : (plan.last_page + 1) * 4]
        )
        protected_ok = (
            not options.protected_verify
            or plan.baseline_dump is None
            or self._type2_protected_unchanged(
                plan.baseline_dump,
                dump,
                plan.profile,
                affected_last_page=plan.last_page,
            )
        )
        passed = area == plan.target_area and protected_ok
        self.add_check(
            report,
            CheckItem(
                self._operation_check_name(options),
                CheckState.OK if passed else CheckState.ERROR,
                self.t(
                    "writer.clear_ndef_ok_actual"
                    if options.scope == ERASE_SCOPE_NDEF
                    else "writer.zero_user_ok_actual",
                    changed=plan.changed_page_count,
                    total=plan.page_count,
                )
                if passed
                else self.t("writer.erase_compare_failed"),
                blocking=not passed,
            ),
        )
        if not passed:
            report.summary = self.t("writer.erase_compare_failed")
        return passed

    def _operation_check_name(self, options: Type2EraseOptions) -> str:
        return self.t(
            "writer.clear_ndef_content"
            if options.scope == ERASE_SCOPE_NDEF
            else "writer.zero_user_area"
        )

    @staticmethod
    def _page_slice(data: bytes, first_page: int, page: int) -> bytes:
        offset = (page - first_page) * 4
        return data[offset : offset + 4]

    def _mark_success(
        self, options: Type2EraseOptions, report: WriteReport
    ) -> None:
        report.success = True
        report.verified = bool(options.final_verify)
        uid = hex_uid(report.target_uid_after or report.target_uid_before)
        if options.scope == ERASE_SCOPE_NDEF:
            success_key = (
                "writer.clear_ndef_success"
                if options.final_verify
                else "writer.clear_ndef_success_unverified"
            )
        else:
            success_key = (
                "writer.zero_user_success"
                if options.final_verify
                else "writer.zero_user_success_unverified"
            )
        report.summary = self.t(
            success_key, uid=uid or self.t("common.unknown")
        )
