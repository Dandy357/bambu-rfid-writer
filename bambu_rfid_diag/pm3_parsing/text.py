from __future__ import annotations

import re


ANSI_RE = re.compile(
    r"(?:\x1B\[[0-?]*[ -/]*[@-~])|(?:\x1B\][^\x07]*(?:\x07|\x1B\\))"
)


def clean_output(text: str) -> str:
    """Remove terminal control sequences and normalize Proxmark output."""
    text = ANSI_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x08", "")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def line_value(text: str, label: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*(?:\[[^\]]+\]\s*)?{re.escape(label)}\.*\s+(.+?)\s*$",
        text,
    )
    return match.group(1).strip() if match else None


def section_first_value(text: str, section: str) -> str | None:
    """Return the first data line below a section header such as Client."""
    lines = text.splitlines()
    header = re.compile(
        rf"^\s*\[\s*{re.escape(section)}\s*\]\s*$", re.IGNORECASE
    )
    for index, line in enumerate(lines):
        if not header.match(line):
            continue
        for candidate in lines[index + 1 :]:
            value = candidate.strip()
            if not value:
                continue
            if re.fullmatch(r"\[.*\]", value):
                break
            return value
    return None


def hardware_value(text: str, label: str) -> str | None:
    """Read a detailed ``--= label: value`` line from ``hw version``."""
    match = re.search(
        rf"(?im)^\s*--=\s*{re.escape(label)}(?:\s*:\s*|\s+)(.+?)\s*$",
        text,
    )
    return match.group(1).strip() if match else None


def commit_hash(version: str | None) -> str | None:
    if not version:
        return None
    match = re.search(r"-g([0-9a-f]{7,40})(?:\b|-)", version, re.IGNORECASE)
    return match.group(1).lower() if match else None


def first_hex_field(
    text: str,
    label: str,
    min_bytes: int,
    max_bytes: int,
) -> str | None:
    """Read the contiguous hexadecimal byte sequence directly after a label."""
    for line in text.splitlines():
        if not re.search(rf"\b{re.escape(label)}\b\s*:", line, re.IGNORECASE):
            continue
        tail = line.split(":", 1)[1]
        byte_prefix = re.match(r"\s*((?:[0-9A-Fa-f]{2}(?:\s+|$))+)", tail)
        if not byte_prefix:
            continue
        values = re.findall(r"[0-9A-Fa-f]{2}", byte_prefix.group(1))
        if min_bytes <= len(values) <= max_bytes:
            return " ".join(value.upper() for value in values)
        if len(values) > max_bytes:
            return " ".join(value.upper() for value in values[:max_bytes])
    return None


def config_hex_line(
    text: str,
    label_pattern: str,
    byte_count: tuple[int, int],
) -> str | None:
    pattern = re.compile(label_pattern, re.IGNORECASE)
    for line in text.splitlines():
        if not pattern.search(line):
            continue
        tail = line.split(":", 1)[1] if ":" in line else line
        values = re.findall(r"\b[0-9A-Fa-f]{2}\b", tail)
        if byte_count[0] <= len(values) <= byte_count[1]:
            return " ".join(value.upper() for value in values)
        if len(values) > byte_count[1]:
            return " ".join(value.upper() for value in values[: byte_count[1]])
    return None
