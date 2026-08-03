from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OperationEventName(StrEnum):
    """Stable event names emitted by PM3 sessions and destructive workflows."""

    OPERATION_STARTED = "operation_started"
    PROGRESS = "progress"
    SESSION_STARTED = "session_started"
    COMMAND_STARTED = "command_started"
    COMMAND_OUTPUT = "command_output"
    COMMAND_FINISHED = "command_finished"
    CHECK_ADDED = "check_added"
    OPERATION_FINISHED = "operation_finished"


class UiEventKind(StrEnum):
    """Events sent from worker threads to the Tkinter event loop."""

    PROGRESS = "progress"
    LIVE = "live"
    WRITE_DONE = "write_done"
    DIAGNOSTIC_DONE = "diag_done"
    NDEF_READ_DONE = "ndef_read_done"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class UiEvent:
    """One typed message waiting for processing on the Tkinter thread."""

    kind: UiEventKind
    mode: str | None = None
    payload: Any = None
    details: str | None = None

    @classmethod
    def progress(cls, message: str) -> "UiEvent":
        return cls(UiEventKind.PROGRESS, payload=message)

    @classmethod
    def live(cls, mode: str, name: str, payload: object) -> "UiEvent":
        return cls(UiEventKind.LIVE, mode=mode, payload=(name, payload))

    @classmethod
    def write_done(cls, mode: str, report: object) -> "UiEvent":
        return cls(UiEventKind.WRITE_DONE, mode=mode, payload=report)

    @classmethod
    def diagnostic_done(cls, mode: str, report: object) -> "UiEvent":
        return cls(UiEventKind.DIAGNOSTIC_DONE, mode=mode, payload=report)

    @classmethod
    def ndef_read_done(cls, result: object) -> "UiEvent":
        return cls(UiEventKind.NDEF_READ_DONE, mode="type2", payload=result)

    @classmethod
    def fatal(cls, mode: str, message: str, details: str) -> "UiEvent":
        return cls(UiEventKind.FATAL, mode=mode, payload=message, details=details)
