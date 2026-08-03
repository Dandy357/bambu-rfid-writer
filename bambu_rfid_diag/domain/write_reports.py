from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .checks import CheckItem
from .commands import CommandResult
from .operations import OperationKind


@dataclass(slots=True)
class WriteReport:
    """Complete technical record of one destructive RFID operation."""

    operation_kind: OperationKind
    operation: str
    started_at_iso: str
    finished_at_iso: str = ""
    success: bool = False
    no_change: bool = False
    verified: bool | None = None
    summary: str = ""
    source_description: str = ""
    source_uid: str | None = None
    target_uid_before: str | None = None
    target_uid_after: str | None = None
    checks: list[CheckItem] = field(default_factory=list)
    commands: list[CommandResult] = field(default_factory=list)
    backup_path: Path | None = None
    report_path: Path | None = None
    locale: str = "en"
    pm3_sessions: int = 0
    profile: str = ""
    method: str = ""
    target_classification: str = ""
    authentication_source: str = ""
