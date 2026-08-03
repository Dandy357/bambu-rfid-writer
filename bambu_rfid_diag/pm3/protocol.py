from __future__ import annotations

import re

from ..pm3_parsing import clean_output


ANSI_BYTES_RE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")

# The PM3 client uses a 256-byte fgets buffer when stdin is redirected.
# Keep headroom for the newline and future client-side processing.
PM3_PIPE_SAFE_COMMAND_LENGTH = 240


def decode_output(data: bytes) -> str:
    """Decode PM3 output using the least-lossy supported Windows encoding."""
    if not data:
        return ""
    candidates: list[tuple[int, str]] = []
    for encoding in ("utf-8", "cp1250", "cp437"):
        decoded = data.decode(encoding, errors="replace")
        candidates.append((decoded.count("\ufffd"), decoded))
    return clean_output(min(candidates, key=lambda item: item[0])[1])



def marker_completed(data: bytes, marker: bytes) -> bool:
    """Return true after PM3 echoed and executed one marker command."""
    return data.count(marker) >= 2


def strip_marker_lines(output: str, marker: str) -> str:
    """Remove internal marker commands and remarks from user-visible output."""
    if not output or marker not in output:
        return output
    kept = [line for line in output.splitlines() if marker not in line]
    return "\n".join(kept).strip()


def infer_command_returncode(output: str) -> int:
    """Provide a conservative fallback result for commands without a parser."""
    lowered = output.lower()
    explicit_failures = (
        "[brw-error]",
        "unknown command",
        "unexpected argument",
        "invalid argument",
        "no tag found",
        "card not found",
        "can't select card",
        "unable to select tag",
        "tag type not detected",
        "timeout while waiting for reply",
        "command execution time out",
        "no response from proxmark3",
        "failed to write",
        "failed to read",
        "failed convert on load",
        "invalid dump",
        "dump file is too small",
        "wrong page count",
        "could not open",
        "couldn't open",
        "operation aborted",
        "( fail )",
    )
    return 1 if any(token in lowered for token in explicit_failures) else 0
