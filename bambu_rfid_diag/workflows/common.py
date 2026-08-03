from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..domain.errors import ConfigurationError
from ..domain.operation_events import OperationEventName
from ..domain.write_reports import WriteReport
from ..i18n import Translator, normalize_locale
from ..material_library import scan_material_library, uid_index
from ..domain import CheckItem, CheckState, CommandResult, HardwareInfo, TagInfo
from ..nfc_type2 import MFU_HEADER_SIZE, parse_mfu_dump
from ..options import (
    MfcWriteOptions,
    PROFILE_RECOMMENDED,
    TimeoutOptions,
    Type2EraseOptions,
    Type2WriteOptions,
    TYPE2_METHOD_RAW,
    TYPE2_METHOD_WRBL,
)
from ..pm3_parsing import DefaultKeyCheck
from ..pm3 import (
    OperationCancelledError,
    ProxmarkWriteRunner,
    resolve_bundle,
    validate_port,
)
from ..pm3.results import (
    mark_failed,
    mfc_dump_succeeded,
    mfc_restore_succeeded,
    mfu_dump_succeeded,
    mfu_restore_succeeded,
    mfu_wrbl_batch_succeeded,
    raw_page_batch_succeeded,
)
from ..sources import MfcSource, load_mfc_source
from ..type2 import Type2Profile
from .preflight_mifare import run_mifare_preflight
from .preflight_type2 import run_type2_preflight


ProgressCallback = Callable[[str], None]
OperationEventCallback = Callable[[str, object], None]
RunnerFactory = Callable[..., ProxmarkWriteRunner]

LOGGER = logging.getLogger(__name__)

PM3_PIPE_PAGE_BATCH = 7

_FIRMWARE_CACHE_LOCK = threading.Lock()
_FIRMWARE_OK_CACHE: set[tuple[str, ...]] = set()


@dataclass(frozen=True, slots=True)
class WorkflowDependencies:
    """External services used by destructive workflows."""

    resolve_bundle: Callable = resolve_bundle
    validate_port: Callable = validate_port
    runner_factory: RunnerFactory = ProxmarkWriteRunner
    scan_material_library: Callable = scan_material_library
    uid_index: Callable = uid_index
    load_mfc_source: Callable = load_mfc_source
    app_data_directory: Callable[[], Path] | None = None
    save_report: Callable[[WriteReport], Path] | None = None



def bundle_fingerprint(layout: object) -> tuple[str, ...]:
    """Return a stable cache identity that changes when PM3 executables change."""

    parts: list[str] = []
    root = getattr(layout, "root", None)
    if root is not None:
        parts.append(str(Path(root).resolve()).casefold())
    for attribute in ("pm3_bat", "setup_bat", "pm3_script", "proxmark_exe"):
        value = getattr(layout, attribute, None)
        if value is None:
            continue
        path = Path(value)
        try:
            stat = path.stat()
        except OSError:
            parts.extend((attribute, str(path).casefold(), "missing"))
        else:
            parts.extend(
                (attribute, str(path).casefold(), str(stat.st_size), str(stat.st_mtime_ns))
            )
    return tuple(parts)

def clear_firmware_cache() -> None:
    with _FIRMWARE_CACHE_LOCK:
        _FIRMWARE_OK_CACHE.clear()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def command_ok(result: CommandResult) -> bool:
    return not result.timed_out and result.returncode == 0


def read_exact_output(path: Path, locale: str = "en") -> bytes:
    for candidate in (path, Path(str(path) + ".bin")):
        if candidate.is_file():
            return candidate.read_bytes()
    raise FileNotFoundError(
        Translator(locale).t("writer.file_missing", name=path.name)
    )


def unique_atoms(atoms: list[str]) -> str:
    result: list[str] = []
    for atom in atoms:
        if atom not in result:
            result.append(atom)
    return "; ".join(result)


def hex_uid(value: str | None) -> str:
    return (value or "").replace(" ", "").upper()


def build_mfu_restore_image(
    base_data: bytes,
    tlv: bytes,
    *,
    page4_valid: bool,
    profile: Type2Profile,
    locale: str = "en",
) -> bytes:
    parsed = parse_mfu_dump(base_data)
    if parsed.max_page < (profile.max_page or profile.ndef_last_page):
        raise ValueError(
            Translator(normalize_locale(locale)).t(
                "writer.restore_profile_mismatch",
                profile=profile.display_name,
            )
        )
    if len(tlv) > profile.ndef_capacity:
        raise ValueError(
            Translator(normalize_locale(locale)).t(
                "writer.restore_capacity_mismatch",
                bytes=len(tlv),
                profile=profile.display_name,
                capacity=profile.ndef_capacity,
            )
        )
    image = bytearray(base_data)
    ndef_start = MFU_HEADER_SIZE + profile.ndef_first_page * 4
    ndef_end = MFU_HEADER_SIZE + (profile.ndef_last_page + 1) * 4
    image[ndef_start:ndef_end] = b"\x00" * (ndef_end - ndef_start)
    padded = tlv + b"\x00" * ((4 - len(tlv) % 4) % 4)
    image[ndef_start : ndef_start + len(padded)] = padded
    if not page4_valid:
        image[ndef_start : ndef_start + 4] = b"\x00" * 4
    return bytes(image)


class WorkflowBase:
    """Shared orchestration services for one destructive operation."""

    def __init__(
        self,
        *,
        locale: str = "en",
        timeouts: TimeoutOptions | None = None,
        cancel_event: threading.Event | None = None,
        on_event: OperationEventCallback | None = None,
        dependencies: WorkflowDependencies | None = None,
    ) -> None:
        self.locale = normalize_locale(locale)
        self.tr = Translator(self.locale)
        self.t = self.tr.t
        self.timeouts = (timeouts or TimeoutOptions()).normalized()
        self.cancel_event = cancel_event
        self.on_event = on_event
        self.dependencies = dependencies or WorkflowDependencies()
        self._firmware_cache_key: tuple[str, ...] | None = None

    def _copy_persistent_backup(
        self, source: Path, prefix: str, uid: str
    ) -> Path:
        if self.dependencies.app_data_directory is None:
            raise ConfigurationError(
                "Application data directory dependency is not configured"
            )
        directory = self.dependencies.app_data_directory() / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (
            f"{prefix}_{safe_timestamp()}_{uid or 'NOUID'}.bin"
        )
        shutil.copyfile(source, destination)
        return destination

    def _emit(self, event: str, payload: object) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event, payload)
        except Exception:
            LOGGER.exception("Operation event callback failed for %s", event)

    def _progress_callback(
        self, callback: ProgressCallback | None
    ) -> ProgressCallback:
        target = callback or (lambda _message: None)

        def emit(message: str) -> None:
            target(message)
            self._emit(OperationEventName.PROGRESS, message)

        return emit

    def add_check(self, report: WriteReport, check: CheckItem) -> None:
        report.checks.append(check)
        self._emit(OperationEventName.CHECK_ADDED, check)

    @staticmethod
    def command_succeeded(result: CommandResult) -> bool:
        return command_ok(result)

    @staticmethod
    def _validate_mfc_dump(result: CommandResult, path: Path) -> bool:
        valid = mfc_dump_succeeded(result, path)
        if not valid:
            mark_failed(result)
        return valid

    @staticmethod
    def _validate_mfu_dump(result: CommandResult, path: Path) -> bool:
        valid = mfu_dump_succeeded(result, path)
        if not valid:
            mark_failed(result)
        return valid

    @staticmethod
    def _validate_mfc_restore(result: CommandResult) -> bool:
        valid = mfc_restore_succeeded(result)
        if not valid:
            mark_failed(result)
        return valid

    @staticmethod
    def _validate_mfu_restore(result: CommandResult) -> bool:
        valid = mfu_restore_succeeded(result)
        if not valid:
            mark_failed(result)
        return valid

    @staticmethod
    def unique_atoms(atoms: list[str]) -> str:
        return unique_atoms(atoms)

    def _runner(
        self, bundle_root: str | Path, port: str | None
    ) -> tuple[object, ProxmarkWriteRunner]:
        layout = self.dependencies.resolve_bundle(bundle_root, self.locale)
        requested_port = self.dependencies.validate_port(port, self.locale)
        self._firmware_cache_key = (
            *bundle_fingerprint(layout),
            requested_port or "AUTO",
        )
        return layout, self.dependencies.runner_factory(
            layout,
            requested_port,
            locale=self.locale,
            timeouts=self.timeouts,
            cancel_event=self.cancel_event,
            on_event=self.on_event,
        )

    def firmware_cached(self, profile: str, enabled: bool) -> bool:
        if (
            not enabled
            or profile != PROFILE_RECOMMENDED
            or self._firmware_cache_key is None
        ):
            return False
        with _FIRMWARE_CACHE_LOCK:
            return self._firmware_cache_key in _FIRMWARE_OK_CACHE

    def remember_firmware_match(self, profile: str, passed: bool) -> None:
        if (
            not passed
            or profile != PROFILE_RECOMMENDED
            or self._firmware_cache_key is None
        ):
            return
        with _FIRMWARE_CACHE_LOCK:
            _FIRMWARE_OK_CACHE.add(self._firmware_cache_key)

    def _preflight_mfc(
        self,
        runner: ProxmarkWriteRunner,
        options: MfcWriteOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> tuple[HardwareInfo, TagInfo, DefaultKeyCheck, bool]:
        return run_mifare_preflight(
            self, runner, options, report, progress
        )

    def _preflight_type2(
        self,
        runner: ProxmarkWriteRunner,
        options: Type2WriteOptions | Type2EraseOptions,
        report: WriteReport,
        progress: ProgressCallback,
    ) -> tuple[HardwareInfo, TagInfo, bool]:
        return run_type2_preflight(
            self, runner, options, report, progress
        )

    def _type2_protected_unchanged(
        self,
        before,
        after,
        profile: Type2Profile,
        *,
        affected_last_page: int | None = None,
    ) -> bool:
        protected_tail = (
            (
                affected_last_page
                if affected_last_page is not None
                else profile.ndef_last_page
            )
            + 1
        ) * 4
        return bool(
            after.uid == before.uid
            and after.static_lock == before.static_lock
            and after.dynamic_lock == before.dynamic_lock
            and after.auth0 == before.auth0
            and after.pages[: profile.ndef_first_page * 4]
            == before.pages[: profile.ndef_first_page * 4]
            and after.pages[protected_tail:] == before.pages[protected_tail:]
        )

    def _write_pages(
        self,
        runner: ProxmarkWriteRunner,
        method: str,
        pages: list[tuple[int, bytes]],
        *,
        max_page: int = 127,
        progress: ProgressCallback | None = None,
    ) -> list[CommandResult]:
        if method not in (TYPE2_METHOD_RAW, TYPE2_METHOD_WRBL):
            raise ValueError(self.t("writer.restore_requires_image"))
        batches = [
            pages[index : index + PM3_PIPE_PAGE_BATCH]
            for index in range(0, len(pages), PM3_PIPE_PAGE_BATCH)
        ]
        results: list[CommandResult] = []
        for index, batch in enumerate(batches, start=1):
            if progress is not None:
                progress(
                    self.t(
                        "writer.page_batch_progress",
                        current=index,
                        total=len(batches),
                        first=batch[0][0],
                        last=batch[-1][0],
                    )
                )
            if method == TYPE2_METHOD_RAW:
                try:
                    result = runner.write_mfu_pages_raw(
                        batch, max_page=max_page
                    )
                except TypeError as exc:
                    if "max_page" not in str(exc):
                        raise
                    result = runner.write_mfu_pages_raw(batch)
            else:
                try:
                    result = runner.write_mfu_pages(
                        batch, max_page=max_page
                    )
                except TypeError as exc:
                    if "max_page" not in str(exc):
                        raise
                    result = runner.write_mfu_pages(batch)

            if method == TYPE2_METHOD_RAW:
                valid = raw_page_batch_succeeded(result, len(batch))
            else:
                valid = mfu_wrbl_batch_succeeded(result, len(batch))
            if not valid:
                mark_failed(result)

            results.append(result)
            if not command_ok(result):
                break
        return results

    def _find_current_mfc_source(
        self,
        uid_hex: str,
        selected_source: MfcSource,
        library_root: str | Path | None,
    ) -> MfcSource:
        uid_hex = uid_hex.upper()
        if selected_source.uid_hex == uid_hex:
            return selected_source
        if not library_root:
            raise ValueError(
                self.t("writer.current_keys_library_missing", uid=uid_hex)
            )
        nodes = self.dependencies.scan_material_library(
            library_root, self.locale
        )
        matches = self.dependencies.uid_index(nodes).get(uid_hex, [])
        if not matches:
            raise ValueError(
                self.t("writer.current_keys_not_found", uid=uid_hex)
            )
        if len(matches) > 1:
            raise ValueError(
                self.t(
                    "writer.current_keys_ambiguous",
                    uid=uid_hex,
                    count=len(matches),
                )
            )
        return self.dependencies.load_mfc_source(
            matches[0].path, self.locale
        )

    def finish_cancelled(
        self, report: WriteReport, error: OperationCancelledError
    ) -> WriteReport:
        report.summary = str(error)
        self.add_check(
            report,
            CheckItem(
                self.t("writer.operation_cancelled"),
                CheckState.WARNING,
                str(error),
            ),
        )
        return self._finish(report)

    def finish_unexpected(
        self,
        report: WriteReport,
        error: Exception,
        logger: logging.Logger,
    ) -> WriteReport:
        logger.exception("Unexpected workflow failure")
        report.summary = self.t("writer.operation_stopped", error=error)
        self.add_check(
            report,
            CheckItem(
                self.t("writer.unexpected_error"),
                CheckState.ERROR,
                str(error),
                blocking=True,
            ),
        )
        return self._finish(report)

    def _finish(self, report: WriteReport) -> WriteReport:
        if not report.finished_at_iso:
            report.finished_at_iso = now_iso()
        try:
            if self.dependencies.save_report is None:
                raise ConfigurationError(
                    "Report persistence dependency is not configured"
                )
            self.dependencies.save_report(report)
        except OSError as exc:
            self.add_check(
                report,
                CheckItem(
                    self.t("writer.save_report"),
                    CheckState.WARNING,
                    self.t("writer.save_report_failed", error=exc),
                ),
            )
        self._emit(OperationEventName.OPERATION_FINISHED, report)
        return report
