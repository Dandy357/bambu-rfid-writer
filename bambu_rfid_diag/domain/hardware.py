from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HardwareInfo:
    """Parsed client, firmware, connection, and Proxmark hardware details."""

    connected: bool = False
    port: str | None = None
    communication: str | None = None
    mcu: str | None = None
    memory: str | None = None
    target: str | None = None
    client_version: str | None = None
    bootrom_version: str | None = None
    os_version: str | None = None
    version_match: bool | None = None
    mismatch_message: str | None = None
