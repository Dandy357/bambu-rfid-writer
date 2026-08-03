from __future__ import annotations

import re

from ..domain import HardwareInfo
from .text import (
    clean_output,
    commit_hash,
    hardware_value,
    line_value,
    section_first_value,
)


def parse_hardware(text: str) -> HardwareInfo:
    """Parse ``hw version`` output into a stable hardware information model."""
    text = clean_output(text)
    lower = text.lower()
    port_match = re.search(r"(?im)Using UART port\s+([^\s]+)", text)
    communication_match = re.search(
        r"(?im)Communicating with PM3 over\s+(.+?)\s*$", text
    )

    client = line_value(text, "Client") or section_first_value(text, "Client")
    bootrom = line_value(text, "Bootrom")
    os_version = line_value(text, "OS")
    mcu = line_value(text, "MCU") or hardware_value(text, "uC")
    memory = line_value(text, "Memory") or hardware_value(
        text, "Embedded flash memory"
    )
    target = line_value(text, "Target") or line_value(text, "Firmware")

    mismatch_line = None
    for line in text.splitlines():
        normalized = line.lower()
        if "mismatch" in normalized and (
            "firmware" in normalized
            or "client" in normalized
            or "version" in normalized
        ):
            mismatch_line = line.strip()
            break

    hashes = [commit_hash(client), commit_hash(bootrom), commit_hash(os_version)]
    known_hashes = [value for value in hashes if value]
    if mismatch_line:
        version_match: bool | None = False
    elif len(known_hashes) == 3:
        version_match = len(set(known_hashes)) == 1
    else:
        version_match = None

    hard_error_markers = (
        "cannot communicate with the proxmark",
        "no port found",
        "failed to open serial port",
        "could not open serial port",
        "device not found",
    )
    connected = (
        "communicating with pm3" in lower
        or "[usb] pm3" in lower
        or (mcu is not None and not any(x in lower for x in hard_error_markers))
    )

    return HardwareInfo(
        connected=connected,
        port=port_match.group(1).upper() if port_match else None,
        communication=(
            communication_match.group(1).strip() if communication_match else None
        ),
        mcu=mcu,
        memory=memory,
        target=target,
        client_version=client,
        bootrom_version=bootrom,
        os_version=os_version,
        version_match=version_match,
        mismatch_message=mismatch_line,
    )
