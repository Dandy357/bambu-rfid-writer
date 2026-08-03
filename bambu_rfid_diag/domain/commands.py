from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CommandResult:
    """Captured output and timing of one command inside a PM3 session."""

    command: str
    returncode: int
    output: str
    duration_seconds: float
    timed_out: bool = False
    timeout_reason: str | None = None
