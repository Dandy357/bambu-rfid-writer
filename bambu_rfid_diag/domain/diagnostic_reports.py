from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .checks import CheckItem, OverallState
from .commands import CommandResult
from .hardware import HardwareInfo
from .tags import TagInfo


@dataclass(slots=True)
class DiagnosticReport:
    """Complete technical record of one read-only diagnostic operation."""

    started_at_iso: str
    finished_at_iso: str
    bundle_root: Path
    requested_port: str | None
    overall_state: OverallState
    summary: str
    hardware: HardwareInfo
    tag: TagInfo
    checks: list[CheckItem] = field(default_factory=list)
    commands: list[CommandResult] = field(default_factory=list)
    report_path: Path | None = None
    locale: str = "en"
    pm3_sessions: int = 0
