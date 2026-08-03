from __future__ import annotations

import threading
from pathlib import Path

from .domain.write_reports import WriteReport
from .material_library import scan_material_library, uid_index
from .options import MfcWriteOptions, Type2EraseOptions, TimeoutOptions
from .presentation.write_report import (
    backup_directory as _backup_directory,
    save_write_report as _save_write_report,
    write_log_directory as _write_log_directory,
)
from .pm3 import ProxmarkWriteRunner, resolve_bundle, validate_port
from .infrastructure.paths import app_data_directory
from .sources import MfcSource, load_mfc_source
from .workflows.common import (
    PM3_PIPE_PAGE_BATCH,
    OperationEventCallback,
    ProgressCallback,
    WorkflowBase,
    WorkflowDependencies,
    clear_firmware_cache,
)
from .workflows.mfc_clone import MfcCloneWorkflow
from .workflows.type2_erase import Type2EraseWorkflow
from .workflows.type2_write import Type2NdefWriteWorkflow


__all__ = [
    "PM3_PIPE_PAGE_BATCH",
    "WriterService",
    "backup_directory",
    "save_write_report",
    "write_log_directory",
]


def backup_directory() -> Path:
    """Return the persistent backup directory for the current user."""
    return _backup_directory(app_data_directory())


def write_log_directory() -> Path:
    """Return the persistent write-log directory for the current user."""
    return _write_log_directory(app_data_directory())


def save_write_report(report: WriteReport) -> Path:
    """Persist a write report using its stable operation identifier."""
    return _save_write_report(report, data_root=app_data_directory())


def _clear_firmware_cache_for_tests() -> None:
    clear_firmware_cache()


class WriterService:
    """Public facade used by the GUI and external callers.

    Each public method creates one protocol-specific workflow. Legacy NTAG
    method names remain as aliases for compatibility with v0.5 callers.
    """

    def __init__(
        self,
        timeout_seconds: int | None = None,
        locale: str = "en",
        *,
        timeouts: TimeoutOptions | None = None,
        cancel_event: threading.Event | None = None,
        on_event: OperationEventCallback | None = None,
    ) -> None:
        if timeouts is None:
            command = (
                300
                if timeout_seconds is None
                else max(0, int(timeout_seconds))
            )
            timeouts = TimeoutOptions(command_seconds=command)
        self.locale = locale
        self._timeout_options = timeouts.normalized()
        self._cancel_event = cancel_event
        self._event_callback = on_event

    @staticmethod
    def _build_dependencies() -> WorkflowDependencies:
        def persist(report: WriteReport) -> Path:
            return _save_write_report(
                report, data_root=app_data_directory()
            )

        return WorkflowDependencies(
            resolve_bundle=resolve_bundle,
            validate_port=validate_port,
            runner_factory=ProxmarkWriteRunner,
            scan_material_library=scan_material_library,
            uid_index=uid_index,
            load_mfc_source=load_mfc_source,
            app_data_directory=app_data_directory,
            save_report=persist,
        )

    def _workflow(self, workflow_type: type[WorkflowBase]) -> WorkflowBase:
        return workflow_type(
            locale=self.locale,
            timeouts=self._timeout_options,
            cancel_event=self._cancel_event,
            on_event=self._event_callback,
            dependencies=self._build_dependencies(),
        )

    def _write_pages(self, runner, method, pages, *, profile=None):
        """Delegate legacy page-batch writes to the shared workflow base.

        This private compatibility hook remains available for v0.5 tests and
        external diagnostics that exercised the previous monolithic service.
        New code should call a protocol-specific workflow instead.
        """
        workflow = self._workflow(Type2NdefWriteWorkflow)
        max_page = getattr(profile, "ndef_last_page", 127)
        return workflow._write_pages(
            runner,
            method,
            pages,
            max_page=max_page,
        )

    def write_bambu(
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
        workflow = self._workflow(MfcCloneWorkflow)
        return workflow.run(
            bundle_root,
            source_folder,
            port,
            acknowledged_cuid_risk=acknowledged_cuid_risk,
            verify_after_write=verify_after_write,
            options=options,
            library_root=library_root,
            on_progress=on_progress,
        )

    def write_type2(
        self,
        bundle_root: str | Path,
        port: str | None,
        **kwargs,
    ) -> WriteReport:
        """Run the NFC Type 2 NDEF write workflow."""
        workflow = self._workflow(Type2NdefWriteWorkflow)
        return workflow.run(bundle_root, port, **kwargs)

    def write_ntag(
        self,
        bundle_root: str | Path,
        port: str | None,
        **kwargs,
    ) -> WriteReport:
        """Compatibility alias for :meth:`write_type2`."""
        return self.write_type2(bundle_root, port, **kwargs)

    def erase_type2(
        self,
        bundle_root: str | Path,
        port: str | None,
        *,
        options: Type2EraseOptions | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WriteReport:
        """Run the NFC Type 2 NDEF clear or user-area zero workflow."""
        workflow = self._workflow(Type2EraseWorkflow)
        return workflow.run(
            bundle_root,
            port,
            options=options,
            on_progress=on_progress,
        )

    def erase_ntag(
        self,
        bundle_root: str | Path,
        port: str | None,
        *,
        options: Type2EraseOptions | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WriteReport:
        """Compatibility alias for :meth:`erase_type2`."""
        return self.erase_type2(
            bundle_root,
            port,
            options=options,
            on_progress=on_progress,
        )
