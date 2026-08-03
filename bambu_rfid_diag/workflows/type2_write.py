from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from ..domain.errors import WorkflowInvariantError
from ..domain.operation_events import OperationEventName
from ..domain.operations import OperationKind
from ..domain.write_reports import WriteReport
from ..infrastructure import OperationWorkspace
from ..domain import CheckItem, CheckState, TagInfo
from ..nfc_type2 import (
    MfuDump,
    Type2Field,
    build_filament_ndef,
    build_type2_ndef,
    parse_mfu_dump,
    parse_type2_tlvs,
)
from ..options import (
    Type2WriteOptions,
    TYPE2_METHOD_RAW,
    TYPE2_METHOD_RESTORE,
)
from ..pm3 import OperationCancelledError, ProxmarkWriteRunner
from ..type2 import (
    MAX_KNOWN_NDEF_CAPACITY,
    Type2Profile,
    profile_from_identifier,
)
from .common import (
    ProgressCallback,
    WorkflowBase,
    build_mfu_restore_image,
    command_ok,
    hex_uid,
    now_iso,
    read_exact_output,
)


LOGGER = logging.getLogger(__name__)

PageWrite = tuple[int, bytes]


@dataclass(frozen=True, slots=True)
class NdefSource:
    """Encoded NDEF TLV and its user-facing source description."""

    tlv: bytes
    description: str


@dataclass(slots=True)
class Type2WritePlan:
    """Prepared memory image and verification context for one Type 2 write."""

    profile: Type2Profile
    tlv: bytes
    padded_tlv: bytes
    full_target_pages: list[PageWrite]
    changed_target_pages: list[PageWrite]
    target_area: bytes | None = None
    baseline_data: bytes | None = None
    baseline_dump: MfuDump | None = None


class Type2NdefWriteWorkflow(WorkflowBase):
    """Write and verify an NDEF message on a supported NFC Type 2 tag."""

    def run(
        self,
        bundle_root: str | Path,
        port: str | None,
        *,
        fields: list[Type2Field] | None = None,
        brand: str | None = None,
        filament_type: str | None = None,
        purchase_date: str | None = None,
        url: str | None = None,
        verify_after_write: bool | None = None,
        options: Type2WriteOptions | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WriteReport:
        options = self._normalize_options(options, verify_after_write)
        source = self._build_source(
            fields=fields,
            brand=brand,
            filament_type=filament_type,
            purchase_date=purchase_date,
            url=url,
        )
        report = self._create_report(source, options)
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

                profile = self._validate_profile_and_capacity(
                    tag, source.tlv, report
                )
                if profile is None:
                    return self._finish(report)

                plan = self._prepare_write_plan(
                    runner=runner,
                    workspace=workspace,
                    tag=tag,
                    profile=profile,
                    tlv=source.tlv,
                    options=options,
                    report=report,
                    progress=progress,
                )
                if plan is None:
                    return self._finish(report)
                if not self._execute_write(
                    runner, workspace, plan, options, report, progress
                ):
                    return self._finish(report)
                if not self._verify_precommit(
                    runner, workspace, plan, options, report, progress
                ):
                    return self._finish(report)
                if not self._commit(
                    runner, plan, options, report, progress
                ):
                    return self._finish(report)
                if not self._verify_final(
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

    @staticmethod
    def _normalize_options(
        options: Type2WriteOptions | None,
        verify_after_write: bool | None,
    ) -> Type2WriteOptions:
        normalized = options or Type2WriteOptions()
        if verify_after_write is None:
            return normalized
        return replace(normalized, final_verify=verify_after_write)

    def _build_source(
        self,
        *,
        fields: list[Type2Field] | None,
        brand: str | None,
        filament_type: str | None,
        purchase_date: str | None,
        url: str | None,
    ) -> NdefSource:
        if fields is not None:
            tlv = build_type2_ndef(
                fields,
                language=self.locale,
                locale=self.locale,
                capacity=MAX_KNOWN_NDEF_CAPACITY,
            )
            return NdefSource(
                tlv,
                self.t(
                    "writer.ntag_fields_source",
                    count=len(fields),
                    bytes=len(tlv),
                ),
            )

        tlv = build_filament_ndef(
            brand or "",
            filament_type or "",
            purchase_date or "",
            url or "",
            language=self.locale,
            locale=self.locale,
            capacity=MAX_KNOWN_NDEF_CAPACITY,
        )
        return NdefSource(
            tlv,
            self.t("writer.ntag_legacy_source", bytes=len(tlv)),
        )

    def _create_report(
        self, source: NdefSource, options: Type2WriteOptions
    ) -> WriteReport:
        return WriteReport(
            operation_kind=OperationKind.TYPE2_NDEF_WRITE,
            operation=self.t("writer.ntag_operation"),
            started_at_iso=now_iso(),
            locale=self.locale,
            source_description=source.description,
            profile=self.t(f"settings.profile_{options.profile}"),
            method=self.t(f"settings.method_{options.method}"),
        )

    @staticmethod
    def _create_workspace(client_directory: Path) -> OperationWorkspace:
        workspace = OperationWorkspace(client_directory)
        workspace.reserve_many(
            {
                "before": "type2_before.bin",
                "body": "type2_body.bin",
                "verify": "type2_verify.bin",
                "restore": "type2_restore.bin",
            }
        )
        return workspace

    def _validate_profile_and_capacity(
        self, tag: TagInfo, tlv: bytes, report: WriteReport
    ) -> Type2Profile | None:
        profile = profile_from_identifier(tag.type2_profile)
        if profile is None:
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

        fits = len(tlv) <= profile.ndef_capacity
        self.add_check(
            report,
            CheckItem(
                self.t("writer.ndef_capacity_check"),
                CheckState.OK if fits else CheckState.ERROR,
                self.t(
                    "writer.ndef_fits_tag",
                    bytes=len(tlv),
                    capacity=profile.ndef_capacity,
                    profile=profile.display_name,
                )
                if fits
                else self.t(
                    "writer.ndef_too_large_for_tag",
                    bytes=len(tlv),
                    capacity=profile.ndef_capacity,
                    profile=profile.display_name,
                ),
                blocking=not fits,
            ),
        )
        if not fits:
            report.summary = self.t("writer.ndef_too_large")
            return None
        return profile

    def _prepare_write_plan(
        self,
        *,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        tag: TagInfo,
        profile: Type2Profile,
        tlv: bytes,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> Type2WritePlan | None:
        padded = tlv + b"\x00" * ((4 - len(tlv) % 4) % 4)
        simple_pages = self._bytes_to_pages(
            padded, first_page=profile.ndef_first_page
        )
        plan = Type2WritePlan(
            profile=profile,
            tlv=tlv,
            padded_tlv=padded,
            full_target_pages=simple_pages,
            changed_target_pages=simple_pages,
        )
        if not self._baseline_required(options):
            return plan

        baseline = self._read_baseline(
            runner,
            workspace,
            tag,
            profile,
            options,
            report,
            progress,
        )
        if baseline is None:
            return None
        baseline_data, baseline_dump, current_area = baseline
        target_area = tlv + b"\x00" * (
            profile.ndef_capacity - len(tlv)
        )
        full_pages = self._bytes_to_pages(
            target_area, first_page=profile.ndef_first_page
        )
        changed_pages = [
            item
            for item in full_pages
            if self._current_page(current_area, profile, item[0]) != item[1]
        ]
        plan.baseline_data = baseline_data
        plan.baseline_dump = baseline_dump
        plan.target_area = target_area
        plan.full_target_pages = full_pages
        plan.changed_target_pages = changed_pages
        return plan

    @staticmethod
    def _baseline_required(options: Type2WriteOptions) -> bool:
        return bool(
            options.backup
            or options.target_stability
            or options.method == TYPE2_METHOD_RESTORE
            or (
                options.protected_verify
                and (options.precommit_verify or options.final_verify)
            )
        )

    def _read_baseline(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        tag: TagInfo,
        profile: Type2Profile,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> tuple[bytes, MfuDump, bytes] | None:
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
        if not self._validate_baseline_profile(dump, profile, report):
            return None
        area = bytes(
            dump.pages[
                profile.ndef_first_page * 4 : (profile.ndef_last_page + 1)
                * 4
            ]
        )
        if not self._validate_standard_tlv_layout(area, report):
            return None
        if not self._validate_target_stability(
            tag, dump, options, report
        ):
            return None
        self._save_baseline_if_requested(
            workspace, data, dump, area, options, report
        )
        return data, dump, area

    def _validate_baseline_profile(
        self,
        dump: MfuDump,
        profile: Type2Profile,
        report: WriteReport,
    ) -> bool:
        if (
            dump.profile is None
            or dump.profile.identifier == profile.identifier
        ):
            return True
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
        return False

    def _validate_standard_tlv_layout(
        self, area: bytes, report: WriteReport
    ) -> bool:
        try:
            records = parse_type2_tlvs(area, self.locale)
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
            report.summary = self.t("writer.ndef_layout_unsafe")
            return False

        ndef_count = sum(record.tlv_type == 0x03 for record in records)
        foreign_count = sum(
            record.tlv_type not in {0x00, 0x03, 0xFE}
            for record in records
        )
        standard = ndef_count <= 1 and foreign_count == 0
        self.add_check(
            report,
            CheckItem(
                self.t("writer.ndef_tlv_map"),
                CheckState.OK if standard else CheckState.ERROR,
                self.t("writer.ndef_layout_standard")
                if standard
                else self.t(
                    "writer.ndef_layout_nonstandard",
                    records=foreign_count,
                    ndef=ndef_count,
                ),
                blocking=not standard,
            ),
        )
        if not standard:
            report.summary = self.t("writer.ndef_layout_unsafe")
        return standard

    def _validate_target_stability(
        self,
        tag: TagInfo,
        dump: MfuDump,
        options: Type2WriteOptions,
        report: WriteReport,
    ) -> bool:
        if not report.target_uid_before:
            report.target_uid_before = " ".join(
                f"{byte:02X}" for byte in dump.uid
            )
        if not options.target_stability:
            return True

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
        return passed

    def _save_baseline_if_requested(
        self,
        workspace: OperationWorkspace,
        data: bytes,
        dump: MfuDump,
        area: bytes,
        options: Type2WriteOptions,
        report: WriteReport,
    ) -> None:
        if not options.backup:
            return
        save_empty = options.profile == "thorough"
        if save_empty or any(area):
            report.backup_path = self._copy_persistent_backup(
                workspace.paths["before"],
                "ntag_before_write",
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

    @staticmethod
    def _bytes_to_pages(
        data: bytes, *, first_page: int
    ) -> list[PageWrite]:
        return [
            (first_page + index // 4, data[index : index + 4])
            for index in range(0, len(data), 4)
        ]

    @staticmethod
    def _current_page(
        area: bytes, profile: Type2Profile, page: int
    ) -> bytes:
        offset = (page - profile.ndef_first_page) * 4
        return area[offset : offset + 4]

    def _execute_write(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if options.method == TYPE2_METHOD_RESTORE:
            return self._execute_restore(
                runner, workspace, plan, options, report, progress
            )
        if options.two_phase:
            return self._execute_two_phase_body(
                runner, plan, options, report, progress
            )
        return self._execute_direct_write(
            runner, plan, options, report, progress
        )

    def _execute_restore(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if plan.baseline_data is None:
            raise WorkflowInvariantError(
                "Type 2 restore requires a complete baseline dump"
            )
        image = build_mfu_restore_image(
            plan.baseline_data,
            plan.tlv,
            page4_valid=not options.two_phase,
            profile=plan.profile,
            locale=self.locale,
        )
        workspace.paths["restore"].write_bytes(image)
        progress(self.t("writer.restore_ntag_progress"))
        result = runner.restore_mfu(workspace.names["restore"])
        report.commands.append(result)
        if self._validate_mfu_restore(result):
            return True
        report.summary = self.t("writer.ntag_write_failed")
        return False

    def _execute_two_phase_body(
        self,
        runner: ProxmarkWriteRunner,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        progress(self.t("writer.invalidate_progress"))
        invalidate = self._write_pages(
            runner,
            options.method,
            [(plan.profile.ndef_first_page, b"\x00" * 4)],
            max_page=plan.profile.ndef_last_page,
            progress=progress,
        )
        report.commands.extend(invalidate)
        if not all(command_ok(result) for result in invalidate):
            report.summary = self.t("writer.invalidate_failed")
            return False

        body_pages = [
            item
            for item in plan.changed_target_pages
            if item[0] != plan.profile.ndef_first_page
        ]
        if not body_pages:
            return True
        progress(
            self.t("writer.write_body_progress", pages=len(body_pages))
        )
        results = self._write_pages(
            runner,
            options.method,
            body_pages,
            max_page=plan.profile.ndef_last_page,
            progress=progress,
        )
        report.commands.extend(results)
        if all(command_ok(result) for result in results):
            return True
        report.summary = self.t("writer.body_write_failed")
        return False

    def _execute_direct_write(
        self,
        runner: ProxmarkWriteRunner,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        progress(
            self.t(
                "writer.write_body_progress",
                pages=len(plan.changed_target_pages),
            )
        )
        results = (
            self._write_pages(
                runner,
                options.method,
                plan.changed_target_pages,
                max_page=plan.profile.ndef_last_page,
                progress=progress,
            )
            if plan.changed_target_pages
            else []
        )
        report.commands.extend(results)
        if all(command_ok(result) for result in results):
            return True
        report.summary = self.t("writer.ntag_write_failed")
        return False

    def _verify_precommit(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if not (options.two_phase and options.precommit_verify):
            return True
        progress(self.t("writer.precommit_progress"))
        result = runner.dump_mfu(workspace.names["body"])
        report.commands.append(result)
        if not self._validate_mfu_dump(result, workspace.paths["body"]):
            report.summary = self.t("writer.body_verify_failed")
            return False

        dump = parse_mfu_dump(
            read_exact_output(workspace.paths["body"], self.locale),
            self.locale,
        )
        expected = (
            b"\x00" * 4 + plan.target_area[4:]
            if plan.target_area is not None
            else b"\x00" * 4 + plan.padded_tlv[4:]
        )
        start = plan.profile.ndef_first_page * 4
        actual = dump.pages[start : start + len(expected)]
        protected_ok = (
            not options.protected_verify
            or plan.baseline_dump is None
            or self._type2_protected_unchanged(
                plan.baseline_dump, dump, plan.profile
            )
        )
        passed = actual == expected and protected_ok
        self.add_check(
            report,
            CheckItem(
                self.t("writer.precommit_check"),
                CheckState.OK if passed else CheckState.ERROR,
                self.t("writer.body_ok")
                if passed
                else self.t("writer.body_mismatch"),
                blocking=not passed,
            ),
        )
        if not passed:
            report.summary = self.t("writer.body_mismatch")
        return passed

    def _commit(
        self,
        runner: ProxmarkWriteRunner,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if not options.two_phase:
            return True
        progress(self.t("writer.commit_progress"))
        method = (
            TYPE2_METHOD_RAW
            if options.method == TYPE2_METHOD_RESTORE
            else options.method
        )
        results = self._write_pages(
            runner,
            method,
            [plan.full_target_pages[0]],
            max_page=plan.profile.ndef_last_page,
            progress=progress,
        )
        report.commands.extend(results)
        if all(command_ok(result) for result in results):
            return True
        report.summary = self.t("writer.commit_failed")
        return False

    def _verify_final(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        plan: Type2WritePlan,
        options: Type2WriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if not options.final_verify:
            return True
        progress(self.t("writer.verify_ntag_progress"))
        result = runner.dump_mfu(workspace.names["verify"])
        report.commands.append(result)
        if not self._validate_mfu_dump(result, workspace.paths["verify"]):
            report.summary = self.t("writer.verify_ntag_failed")
            return False

        dump = parse_mfu_dump(
            read_exact_output(workspace.paths["verify"], self.locale),
            self.locale,
        )
        report.target_uid_after = dump.uid.hex().upper()
        start = plan.profile.ndef_first_page * 4
        expected = (
            plan.target_area
            if plan.target_area is not None
            else plan.tlv
        )
        readback = dump.pages[start : start + len(expected)]
        protected_ok = (
            not options.protected_verify
            or plan.baseline_dump is None
            or self._type2_protected_unchanged(
                plan.baseline_dump, dump, plan.profile
            )
        )
        passed = readback == expected and protected_ok
        self.add_check(
            report,
            CheckItem(
                self.t("writer.post_compare"),
                CheckState.OK if passed else CheckState.ERROR,
                self.t(
                    "writer.ntag_compare_ok_actual",
                    bytes=len(plan.tlv),
                    changed=len({page for page, _data in plan.changed_target_pages}),
                    first=min(
                        (page for page, _data in plan.changed_target_pages),
                        default=plan.profile.ndef_first_page,
                    ),
                    last=max(
                        (page for page, _data in plan.changed_target_pages),
                        default=plan.profile.ndef_first_page,
                    ),
                )
                if passed
                else self.t(
                    "writer.post_compare_failed",
                    reason=self.t("writer.bytes_mismatch"),
                ),
                blocking=not passed,
            ),
        )
        if not passed:
            report.summary = self.t(
                "writer.post_compare_failed",
                reason=self.t("writer.bytes_mismatch"),
            )
        return passed

    def _mark_success(
        self, options: Type2WriteOptions, report: WriteReport
    ) -> None:
        report.success = True
        report.verified = bool(options.final_verify)
        uid = hex_uid(report.target_uid_after or report.target_uid_before)
        report.summary = (
            self.t(
                "writer.ntag_success",
                uid=uid or self.t("common.unknown"),
            )
            if options.final_verify
            else self.t(
                "writer.ntag_success_unverified",
                uid=uid or self.t("common.unknown"),
            )
        )
