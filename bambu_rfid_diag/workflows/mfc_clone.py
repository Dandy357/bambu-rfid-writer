from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from ..domain.operation_events import OperationEventName
from ..domain.operations import OperationKind
from ..domain.write_reports import WriteReport
from ..infrastructure import OperationWorkspace
from ..domain import CheckItem, CheckState, TagInfo
from ..options import MfcWriteOptions
from ..pm3_parsing import enrich_mifare_info, parse_iso14a
from ..pm3 import OperationCancelledError, ProxmarkWriteRunner
from ..sources import MfcSource, SourceValidationError
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
class MfcTargetPlan:
    """Authentication and baseline state selected for one clone operation."""

    authentication_key_name: str
    use_keyfile_for_authentication: bool = False
    baseline_data: bytes | None = None


class MfcCloneWorkflow(WorkflowBase):
    """Clone one validated Bambu MIFARE Classic image to a target tag."""

    def run(
        self,
        bundle_root: str | Path,
        source_folder: str | Path | MfcSource,
        port: str | None,
        *,
        acknowledged_cuid_risk: bool,
        verify_after_write: bool | None = None,
        options: MfcWriteOptions | None = None,
        library_root: str | Path | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WriteReport:
        options = self._normalize_options(options, verify_after_write)
        report = self._create_report(options)
        progress = self._progress_callback(on_progress)
        workspace: OperationWorkspace | None = None

        self._emit(OperationEventName.OPERATION_STARTED, report)
        try:
            source = self._load_source(source_folder, options, report)
            if not self._confirm_risk_acknowledgement(
                acknowledged_cuid_risk, report
            ):
                return self._finish(report)

            layout, runner = self._runner(bundle_root, port)
            workspace = self._create_workspace(layout.client_dir, source)

            with runner:
                report.pm3_sessions = runner.session_count
                _hardware, tag, key_details, ready = self._preflight_mfc(
                    runner, options, report, progress
                )
                if not ready:
                    report.summary = self.t("writer.bambu_preflight_failed")
                    return self._finish(report)

                target_plan = self._prepare_target(
                    runner=runner,
                    workspace=workspace,
                    source=source,
                    tag=tag,
                    key_details=key_details,
                    options=options,
                    library_root=library_root,
                    report=report,
                    progress=progress,
                )
                if target_plan is None:
                    return self._finish(report)
                if not self._restore_source(
                    runner, workspace, target_plan, report, progress
                ):
                    return self._finish(report)
                if not self._verify_result(
                    runner, workspace, source, options, report, progress
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
        options: MfcWriteOptions | None,
        verify_after_write: bool | None,
    ) -> MfcWriteOptions:
        normalized = options or MfcWriteOptions()
        if verify_after_write is None:
            return normalized
        return replace(
            normalized,
            verify_dump=verify_after_write,
            verify_uid=verify_after_write,
        )

    def _create_report(self, options: MfcWriteOptions) -> WriteReport:
        return WriteReport(
            operation_kind=OperationKind.MFC_CLONE,
            operation=self.t("writer.bambu_operation"),
            started_at_iso=now_iso(),
            locale=self.locale,
            profile=self.t(f"settings.profile_{options.profile}"),
            method=self.t("settings.method_mfc_restore"),
        )

    def _load_source(
        self,
        source_folder: str | Path | MfcSource,
        options: MfcWriteOptions,
        report: WriteReport,
    ) -> MfcSource:
        source = (
            source_folder
            if isinstance(source_folder, MfcSource)
            else self.dependencies.load_mfc_source(
                source_folder, self.locale, options.source
            )
        )
        report.source_description = (
            f"{source.label}; dump={source.dump_path.name}; "
            f"key={source.key_path.name}; SHA-256={source.sha256}"
        )
        report.source_uid = source.uid_hex or None
        self.add_check(
            report,
            CheckItem(
                self.t("writer.source_files"),
                CheckState.OK,
                self.t("writer.source_files_ok"),
            ),
        )
        return source

    def _confirm_risk_acknowledgement(
        self, acknowledged: bool, report: WriteReport
    ) -> bool:
        if acknowledged:
            return True
        report.summary = self.t("writer.risk_not_confirmed")
        self.add_check(
            report,
            CheckItem(
                self.t("writer.risk_check"),
                CheckState.ERROR,
                report.summary,
                blocking=True,
            ),
        )
        return False

    @staticmethod
    def _create_workspace(
        client_directory: Path, source: MfcSource
    ) -> OperationWorkspace:
        workspace = OperationWorkspace(client_directory)
        workspace.reserve_many(
            {
                "source": "source.bin",
                "source_key": "source_key.bin",
                "current_key": "current_key.bin",
                "default_key": "default_key.bin",
                "before": "before.bin",
                "verify": "verify.bin",
            }
        )
        workspace.paths["source"].write_bytes(source.dump_data)
        workspace.paths["source_key"].write_bytes(source.key_data)
        workspace.paths["default_key"].write_bytes(b"\xFF" * 192)
        return workspace

    def _prepare_target(
        self,
        *,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        source: MfcSource,
        tag: TagInfo,
        key_details,
        options: MfcWriteOptions,
        library_root: str | Path | None,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> MfcTargetPlan | None:
        fresh = bool(
            options.default_keys
            and key_details.complete
            and key_details.all_default is True
        )
        programmed = bool(
            options.default_keys
            and key_details.complete
            and key_details.successful_keys == 0
        )
        if programmed:
            return self._prepare_programmed_target(
                runner=runner,
                workspace=workspace,
                source=source,
                tag=tag,
                options=options,
                library_root=library_root,
                report=report,
                progress=progress,
            )
        return self._prepare_factory_or_unchecked_target(
            runner=runner,
            workspace=workspace,
            fresh=fresh,
            options=options,
            report=report,
            progress=progress,
        )

    def _prepare_programmed_target(
        self,
        *,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        source: MfcSource,
        tag: TagInfo,
        options: MfcWriteOptions,
        library_root: str | Path | None,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> MfcTargetPlan | None:
        uid = hex_uid(tag.uid)
        if not uid:
            self._block_current_keys(
                report, self.t("writer.current_uid_unknown")
            )
            return None

        current_source = self._load_current_target_source(
            uid, source, library_root, report
        )
        if current_source is None:
            return None

        workspace.paths["current_key"].write_bytes(current_source.key_data)
        report.target_classification = self.t("writer.target_programmed_pending")
        report.authentication_source = self.t(
            "writer.auth_current_keys",
            uid=current_source.uid_hex,
            file=current_source.key_path.name,
        )
        self.add_check(
            report,
            CheckItem(
                self.t("writer.current_keys"),
                CheckState.OK,
                self.t(
                    "writer.current_keys_found",
                    uid=current_source.uid_hex,
                    file=current_source.key_path.name,
                ),
            ),
        )

        baseline = self._read_programmed_baseline(
            runner, workspace, tag, options, report, progress
        )
        if baseline is None:
            return None
        if baseline == source.dump_data:
            report.success = True
            report.no_change = True
            report.verified = True
            report.target_uid_after = report.target_uid_before
            report.summary = self.t("writer.mfc_already_matches_summary")
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.mfc_already_matches"),
                    CheckState.OK,
                    self.t("writer.mfc_already_matches_detail", bytes=len(baseline)),
                ),
            )
            return None
        report.target_classification = self.t(
            "writer.target_programmed_unsupported"
        )
        report.summary = self.t("writer.programmed_rewrite_unsupported")
        self.add_check(
            report,
            CheckItem(
                self.t("writer.cuid_rewritability"),
                CheckState.UNSUPPORTED,
                report.summary,
                blocking=True,
            ),
        )
        return None

    def _load_current_target_source(
        self,
        uid: str,
        source: MfcSource,
        library_root: str | Path | None,
        report: WriteReport,
    ) -> MfcSource | None:
        try:
            return self._find_current_mfc_source(uid, source, library_root)
        except (OSError, ValueError, SourceValidationError) as exc:
            self._block_current_keys(report, str(exc))
            return None

    def _block_current_keys(self, report: WriteReport, detail: str) -> None:
        self.add_check(
            report,
            CheckItem(
                self.t("writer.current_keys"),
                CheckState.ERROR,
                detail,
                blocking=True,
            ),
        )
        report.summary = self.t("writer.bambu_preflight_failed")

    def _read_programmed_baseline(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        tag: TagInfo,
        options: MfcWriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bytes | None:
        progress(self.t("writer.baseline_progress_mfc"))
        result = runner.dump_mfc(
            workspace.names["current_key"], workspace.names["before"]
        )
        report.commands.append(result)
        if not self._validate_mfc_dump(result, workspace.paths["before"]):
            self._block_current_keys(
                report, self.t("writer.current_keys_dump_failed")
            )
            report.summary = self.t("writer.backup_failed_mfc")
            return None

        baseline = read_exact_output(workspace.paths["before"], self.locale)
        backup_uid = baseline[:4].hex().upper() if len(baseline) >= 4 else ""
        diagnostic_uid = hex_uid(tag.uid)
        valid_bcc = len(baseline) >= 5 and baseline[4] == (
            baseline[0] ^ baseline[1] ^ baseline[2] ^ baseline[3]
        )
        stable = bool(
            backup_uid and backup_uid == diagnostic_uid and valid_bcc
        )
        self.add_check(
            report,
            CheckItem(
                self.t("writer.target_stability"),
                CheckState.OK if stable else CheckState.ERROR,
                self.t("writer.target_stable")
                if stable
                else self.t("writer.backup_uid_invalid"),
                blocking=not stable,
            ),
        )
        if not stable:
            report.summary = self.t("writer.backup_uid_invalid")
            return None

        if options.backup:
            report.backup_path = self._copy_persistent_backup(
                workspace.paths["before"], "mfc_before_write", backup_uid
            )
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.backup_target"),
                    CheckState.OK,
                    self.t(
                        "writer.backup_saved",
                        bytes=len(baseline),
                        path=report.backup_path,
                    ),
                ),
            )
        return baseline

    def _prepare_factory_or_unchecked_target(
        self,
        *,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        fresh: bool,
        options: MfcWriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> MfcTargetPlan | None:
        if fresh:
            report.target_classification = self.t("writer.target_new_cuid")
            report.authentication_source = self.t("writer.auth_default_keys")
        else:
            report.target_classification = self.t("writer.target_unchecked")
            report.authentication_source = self.t(
                "writer.auth_default_assumed"
            )

        save_factory_backup = bool(
            options.backup and options.profile in {"thorough", "custom"}
        )
        baseline: bytes | None = None
        if save_factory_backup:
            progress(self.t("writer.backup_progress_mfc"))
            result = runner.dump_mfc(
                workspace.names["default_key"], workspace.names["before"]
            )
            report.commands.append(result)
            if not self._validate_mfc_dump(result, workspace.paths["before"]):
                report.summary = self.t("writer.backup_failed_mfc")
                return None
            baseline = read_exact_output(
                workspace.paths["before"], self.locale
            )
            report.backup_path = self._copy_persistent_backup(
                workspace.paths["before"],
                "mfc_before_write",
                hex_uid(report.target_uid_before),
            )
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.backup_target"),
                    CheckState.OK,
                    self.t(
                        "writer.backup_saved",
                        bytes=len(baseline),
                        path=report.backup_path,
                    ),
                ),
            )
        elif options.backup:
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.backup_target"),
                    CheckState.SKIPPED,
                    self.t("writer.backup_skipped_factory"),
                ),
            )

        return MfcTargetPlan(
            authentication_key_name=workspace.names["source_key"],
            baseline_data=baseline,
        )

    def _restore_source(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        target_plan: MfcTargetPlan,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        progress(self.t("writer.write_mfc_progress"))
        result = runner.restore_mfc(
            workspace.names["source"],
            target_plan.authentication_key_name,
            use_keyfile_for_auth=target_plan.use_keyfile_for_authentication,
        )
        report.commands.append(result)
        if self._validate_mfc_restore(result):
            return True
        report.summary = self.t("writer.restore_failed")
        self.add_check(
            report,
            CheckItem(
                self.t("writer.write"),
                CheckState.ERROR,
                report.summary,
                blocking=True,
            ),
        )
        return False

    def _verify_result(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        source: MfcSource,
        options: MfcWriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        if options.verify_dump and not self._verify_dump(
            runner, workspace, source, report, progress
        ):
            return False
        if options.verify_uid and not self._verify_uid(
            runner, source, report, progress
        ):
            return False
        return True

    def _verify_dump(
        self,
        runner: ProxmarkWriteRunner,
        workspace: OperationWorkspace,
        source: MfcSource,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        progress(self.t("writer.verify_mfc_progress"))
        result = runner.dump_mfc(
            workspace.names["source_key"], workspace.names["verify"]
        )
        report.commands.append(result)
        if not self._validate_mfc_dump(result, workspace.paths["verify"]):
            report.summary = self.t("writer.verify_mfc_failed")
            return False

        data = read_exact_output(workspace.paths["verify"], self.locale)
        report.target_uid_after = (
            data[:4].hex().upper() if len(data) >= 4 else None
        )
        passed = data == source.dump_data
        self.add_check(
            report,
            CheckItem(
                self.t("writer.post_compare"),
                CheckState.OK if passed else CheckState.ERROR,
                self.t("writer.mfc_compare_ok", bytes=len(data))
                if passed
                else self.t("writer.mfc_compare_bad"),
                blocking=not passed,
            ),
        )
        if not passed:
            report.summary = self.t("writer.mfc_compare_bad")
        return passed

    def _verify_uid(
        self,
        runner: ProxmarkWriteRunner,
        source: MfcSource,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> bool:
        progress(self.t("writer.verify_uid_progress"))
        result = runner.run("hf 14a info; hf mf info")
        report.commands.append(result)
        if not command_ok(result):
            report.summary = self.t("writer.verify_uid_failed")
            return False

        tag = parse_iso14a(result.output, self.locale)
        enrich_mifare_info(tag, result.output, self.locale)
        report.target_uid_after = tag.uid
        passed = hex_uid(tag.uid) == source.uid_hex
        self.add_check(
            report,
            CheckItem(
                self.t("writer.result_uid"),
                CheckState.OK if passed else CheckState.ERROR,
                self.t("writer.uid_ok", uid=source.uid_hex)
                if passed
                else self.t(
                    "writer.uid_bad",
                    expected=source.uid_hex,
                    actual=hex_uid(tag.uid) or "?",
                ),
                blocking=not passed,
            ),
        )
        if not passed:
            report.summary = self.t("writer.verify_uid_failed")
        return passed

    def _mark_success(
        self, options: MfcWriteOptions, report: WriteReport
    ) -> None:
        post_selected = options.verify_dump or options.verify_uid
        report.success = True
        report.verified = bool(post_selected)
        report.summary = (
            self.t("writer.bambu_success")
            if post_selected
            else self.t("writer.bambu_success_unverified")
        )
        self.add_check(
            report,
            CheckItem(
                self.t("writer.ams_risk"),
                CheckState.WARNING,
                self.t("writer.ams_risk_detail"),
            ),
        )
