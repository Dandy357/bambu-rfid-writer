from __future__ import annotations

import logging
import os
import queue
import secrets
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ..i18n import Translator, normalize_locale
from ..domain import CommandResult
from ..options import TimeoutOptions
from .bundle import (
    BundleLayout,
    make_session_batch,
    validate_internal_command,
    validate_port,
    validate_read_only_command,
)
from .errors import (
    OperationCancelledError,
    ProxmarkError,
    UnsafeCommandError,
    UnsupportedPlatformError,
)
from .protocol import (
    PM3_PIPE_SAFE_COMMAND_LENGTH,
    decode_output,
    infer_command_returncode,
    marker_completed,
    strip_marker_lines,
)


LOGGER = logging.getLogger(__name__)


class ProxmarkRunner:
    """Manage one persistent PM3 client session for an entire operation."""

    def __init__(
        self,
        layout: BundleLayout,
        port: str | None = None,
        timeout: int | None = None,
        locale: str = "en",
        *,
        timeouts: TimeoutOptions | None = None,
        cancel_event: threading.Event | None = None,
        on_event: Callable[[str, object], None] | None = None,
    ) -> None:
        self.layout = layout
        self.set_locale(locale)
        self.port = validate_port(port, self.locale)
        if timeouts is None:
            command = 300 if timeout is None else int(timeout)
            timeouts = TimeoutOptions(command_seconds=command)
        self.timeouts = timeouts.normalized()
        self.cancel_event = cancel_event
        self.on_event = on_event
        self.process: subprocess.Popen[bytes] | None = None
        self._reader_thread: threading.Thread | None = None
        self._output_queue: queue.Queue[bytes | None] = queue.Queue()
        self._temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self._started_at = 0.0
        self._closed = False
        self.startup_output = ""
        self.session_count = 0
        self.callback_errors: list[str] = []

    def set_locale(self, locale: str) -> None:
        self.locale = normalize_locale(locale)
        self.tr = Translator(self.locale)

    def __enter__(self) -> "ProxmarkRunner":
        self.open()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def open(self) -> None:
        if self._closed:
            raise ProxmarkError(self.tr.t("proxmark.runner_closed"))
        if self.process is not None:
            if self.process.poll() is None:
                return
            raise ProxmarkError(self.tr.t("proxmark.runner_exited"))
        if os.name != "nt":
            raise UnsupportedPlatformError(self.tr.t("proxmark.windows_only"))
        self._temp_dir = tempfile.TemporaryDirectory(prefix="BambuRFIDSession_")
        batch_path = Path(self._temp_dir.name) / "run_pm3_session.cmd"
        batch_path.write_text(
            make_session_batch(self.layout, self.port, self.locale),
            encoding="mbcs",
            newline="",
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        self.process = subprocess.Popen(
            ["cmd.exe", "/D", "/S", "/C", str(batch_path)],
            cwd=str(self.layout.root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            bufsize=0,
        )
        self._started_at = time.monotonic()
        self.session_count = 1
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

        self._perform_startup_handshake()
        self._emit("session_started", {"sessions": self.session_count})

    def _perform_startup_handshake(self) -> None:
        # Pipe mode has no idle prompt. Execute a harmless marker immediately;
        # its second occurrence confirms that PM3 completed initialization.
        marker = self._new_marker("READY")
        try:
            self._write_line(f"rem {marker}")
        except (BrokenPipeError, OSError) as exc:
            self._terminate_tree()
            raise ProxmarkError(
                self.tr.t(
                    "proxmark.session_start_failed", code=-1, output=str(exc)
                )
            ) from exc
        data, timeout_reason = self._read_until_marker(
            marker,
            timeout_seconds=self.timeouts.startup_seconds,
            timeout_kind="startup",
            enforce_idle=True,
        )
        decoded = decode_output(data)
        self.startup_output = strip_marker_lines(decoded, marker)
        if timeout_reason:
            self._terminate_tree()
            detail = self.tr.t(
                "proxmark.session_start_timeout_reason",
                reason=self.tr.t(f"timeout.reason_{timeout_reason}"),
            )
            if self.startup_output:
                detail = (
                    f"{detail} "
                    f"{self.tr.t('proxmark.captured_output', output=self.startup_output)}"
                )
            raise ProxmarkError(detail)
        if (
            self.process is not None
            and self.process.poll() is not None
            and not marker_completed(data, marker.encode("ascii"))
        ):
            code = (
                self.process.returncode
                if self.process.returncode is not None
                else -1
            )
            self._terminate_tree()
            raise ProxmarkError(
                self.tr.t(
                    "proxmark.session_start_failed",
                    code=code,
                    output=self.startup_output,
                )
            )

    def _emit(self, event: str, payload: object) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event, payload)
        except Exception as exc:  # GUI callbacks are outside the transport trust boundary.
            message = f"{type(exc).__name__}: {exc}"
            self.callback_errors.append(message)
            LOGGER.exception("PM3 event callback failed for %s", event)

    def _emit_output_line(self, raw_line: bytes, marker: bytes) -> None:
        if not raw_line or marker in raw_line:
            return
        text = decode_output(raw_line)
        if text:
            self._emit("command_output", text.rstrip("\r\n"))

    def _reader(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            self._output_queue.put(None)
            return
        try:
            while True:
                chunk = process.stdout.read(1)
                if not chunk:
                    break
                self._output_queue.put(chunk)
        finally:
            self._output_queue.put(None)

    def _new_marker(self, purpose: str) -> str:
        return f"BRW_{purpose}_{secrets.token_hex(8).upper()}"

    def _write_line(self, line: str) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise ProxmarkError(self.tr.t("proxmark.session_not_open"))
        process.stdin.write((line + "\n").encode("ascii"))
        process.stdin.flush()

    def _read_until_marker(
        self,
        marker: str,
        timeout_seconds: int,
        *,
        timeout_kind: str,
        enforce_idle: bool,
    ) -> tuple[bytes, str | None]:
        buffer = bytearray()
        line_buffer = bytearray()
        marker_bytes = marker.encode("ascii")
        command_started = time.monotonic()
        last_output = command_started
        while True:
            self._check_cancelled()
            now = time.monotonic()
            if self._expired(
                self.timeouts.operation_seconds, self._started_at, now
            ):
                return bytes(buffer), "operation"
            if self._expired(timeout_seconds, command_started, now):
                return bytes(buffer), timeout_kind
            if enforce_idle and self._expired(
                self.timeouts.idle_seconds, last_output, now
            ):
                return bytes(buffer), "idle"
            try:
                item = self._output_queue.get(timeout=0.1)
            except queue.Empty:
                if self.process is not None and self.process.poll() is not None:
                    return bytes(buffer), None
                continue
            if item is None:
                return bytes(buffer), None
            buffer.extend(item)
            line_buffer.extend(item)
            last_output = time.monotonic()
            if item in {b"\n", b"\r"}:
                self._emit_output_line(bytes(line_buffer), marker_bytes)
                line_buffer.clear()
            if marker_completed(bytes(buffer), marker_bytes):
                if line_buffer:
                    self._emit_output_line(bytes(line_buffer), marker_bytes)
                return bytes(buffer), None

    @staticmethod
    def _expired(limit: int, started: float, now: float) -> bool:
        return limit > 0 and now - started >= limit

    def _check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            self._terminate_tree()
            raise OperationCancelledError(
                self.tr.t("proxmark.operation_cancelled")
            )

    def run(self, command: str) -> CommandResult:
        command = validate_read_only_command(command, self.locale)
        return self._execute(command)

    def read_mfu_page(self, page: int) -> CommandResult:
        page = int(page)
        if not 0 <= page <= 255:
            raise UnsafeCommandError(
                self.tr.t("proxmark.mfu_read_page_range")
            )
        return self._execute(f"hf mfu rdbl -b {page}")

    def _execute(self, command: str, prefix: str = "BambuRFID_") -> CommandResult:
        del prefix
        validate_internal_command(command, self.tr)
        try:
            command_length = len(command.encode("ascii"))
        except UnicodeEncodeError as exc:
            raise UnsafeCommandError(
                self.tr.t("proxmark.unsafe_internal_command")
            ) from exc
        if command_length > PM3_PIPE_SAFE_COMMAND_LENGTH:
            raise UnsafeCommandError(
                self.tr.t(
                    "proxmark.command_too_long",
                    length=command_length,
                    limit=PM3_PIPE_SAFE_COMMAND_LENGTH,
                )
            )
        self.open()
        process = self.process
        if process is None or process.stdin is None:
            raise ProxmarkError(self.tr.t("proxmark.session_not_open"))
        if process.poll() is not None:
            return CommandResult(
                command, process.returncode or -1, "", 0.0, False
            )

        started = time.monotonic()
        marker = self._new_marker("DONE")
        self._emit("command_started", command)
        try:
            self._write_line(command)
            self._write_line(f"rem {marker}")
        except (BrokenPipeError, OSError, ProxmarkError) as exc:
            result = CommandResult(
                command,
                -1,
                str(exc),
                time.monotonic() - started,
                False,
            )
            self._emit("command_finished", result)
            return result

        data, timeout_reason = self._read_until_marker(
            marker,
            timeout_seconds=self.timeouts.command_seconds,
            timeout_kind="command",
            enforce_idle=True,
        )
        duration = time.monotonic() - started
        decoded = decode_output(data)
        output = strip_marker_lines(decoded, marker)
        if timeout_reason:
            self._terminate_tree()
            result = CommandResult(
                command, -2, output, duration, True, timeout_reason
            )
            self._emit("command_finished", result)
            return result
        if process.poll() is not None and not marker_completed(
            data, marker.encode("ascii")
        ):
            code = process.returncode if process.returncode is not None else -1
            result = CommandResult(command, code, output, duration, False)
            self._emit("command_finished", result)
            return result

        result = CommandResult(
            command, infer_command_returncode(output), output, duration, False
        )
        self._emit("command_finished", result)
        return result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.write(b"quit\n")
                    process.stdin.flush()
                process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self._terminate_tree()
        self._close_process_streams()
        reader = self._reader_thread
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2)
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _close_process_streams(self) -> None:
        process = self.process
        if process is None:
            return
        for stream in (getattr(process, "stdin", None), getattr(process, "stdout", None)):
            if stream is None:
                continue
            close = getattr(stream, "close", None)
            if not callable(close):
                continue
            try:
                close()
            except OSError:
                continue

    def _terminate_tree(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        try:
            process.kill()
        except OSError:
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return
