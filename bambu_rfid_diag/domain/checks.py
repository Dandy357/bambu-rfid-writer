from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CheckState(str, Enum):
    """Severity and completion state of one diagnostic or write check."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    INDETERMINATE = "indeterminate"


class OverallState(str, Enum):
    """High-level result of a read-only diagnostic operation."""

    READY = "ready"
    CAUTION = "caution"
    BLOCKED = "blocked"
    NO_TAG = "no_tag"
    ERROR = "error"


@dataclass(slots=True)
class CheckItem:
    """One localized check result and whether it blocks a destructive action."""

    name: str
    state: CheckState
    detail: str
    blocking: bool = False
