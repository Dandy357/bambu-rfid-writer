from __future__ import annotations

import re
from pathlib import Path

from ..domain.commands import CommandResult

_RAW_ACK_RE = re.compile(r"(?im)^\s*\[\+\]\s*0A\s*$")
_MFU_WRBL_OK_RE = re.compile(r"(?i)Write\s*\(\s*ok\s*\)")
_MFC_RESTORE_BLOCK_OK_RE = re.compile(
    r"(?i)\bblock(?:\.\.\.|\s*)\s*\d+\s*\(\s*ok\s*\)"
)


def transport_succeeded(result: CommandResult) -> bool:
    """Return whether the PM3 transport completed without timeout or failure."""

    return not result.timed_out and result.returncode == 0


def raw_page_batch_succeeded(result: CommandResult, expected_pages: int) -> bool:
    """Require one ISO14443-A ACK for every RAW Type 2 page write."""

    if expected_pages <= 0 or not transport_succeeded(result):
        return False
    return len(_RAW_ACK_RE.findall(result.output)) == expected_pages


def mfu_wrbl_batch_succeeded(result: CommandResult, expected_pages: int) -> bool:
    """Require one explicit successful MFU write result per issued page."""

    if expected_pages <= 0 or not transport_succeeded(result):
        return False
    return len(_MFU_WRBL_OK_RE.findall(result.output)) == expected_pages


def mfc_restore_succeeded(result: CommandResult, expected_blocks: int = 64) -> bool:
    """Require a successful restore status for every MIFARE Classic block."""

    if expected_blocks <= 0 or not transport_succeeded(result):
        return False
    return len(_MFC_RESTORE_BLOCK_OK_RE.findall(result.output)) == expected_blocks


def mfu_restore_succeeded(result: CommandResult) -> bool:
    """Require the explicit start and completion messages from MFU restore."""

    if not transport_succeeded(result):
        return False
    lowered = result.output.lower()
    return "restoring data blocks" in lowered and "done!" in lowered


def mfc_dump_succeeded(
    result: CommandResult,
    path: Path,
    *,
    expected_size: int = 1024,
) -> bool:
    """Validate both PM3's MIFARE dump completion and the staged output file."""

    if not transport_succeeded(result):
        return False
    if "succeeded in dumping all blocks" not in result.output.lower():
        return False
    return _path_has_size(path, expected_size)


def mfu_dump_succeeded(result: CommandResult, path: Path) -> bool:
    """Validate that an MFU dump command produced a plausible binary dump."""

    if not transport_succeeded(result):
        return False
    if "saved" not in result.output.lower():
        return False
    candidate = _existing_output(path)
    if candidate is None:
        return False
    try:
        size = candidate.stat().st_size
    except OSError:
        return False
    # Current MFU binary dumps contain a 56-byte header and at least pages 0-3.
    return size >= 72 and (size - 56) % 4 == 0


def mark_failed(result: CommandResult) -> CommandResult:
    """Convert a transport-successful but semantically incomplete result to failure."""

    if result.returncode == 0:
        result.returncode = 1
    return result


def _path_has_size(path: Path, expected_size: int) -> bool:
    candidate = _existing_output(path)
    if candidate is None:
        return False
    try:
        return candidate.stat().st_size == expected_size
    except OSError:
        return False


def _existing_output(path: Path) -> Path | None:
    for candidate in (path, Path(f"{path}.bin")):
        if candidate.is_file():
            return candidate
    return None
