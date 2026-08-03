"""Compatibility facade for the structured Proxmark3 integration package.

New code should import bundle validation, transport, or typed commands from
:mod:`bambu_rfid_diag.pm3`. Private names are retained where older tests and
external diagnostics relied on them.
"""

from .pm3 import (
    ALLOWED_COMMANDS,
    BundleLayout,
    BundleValidationError,
    OperationCancelledError,
    PM3_PIPE_SAFE_COMMAND_LENGTH,
    ProxmarkError,
    ProxmarkRunner,
    ProxmarkWriteRunner,
    UnsafeCommandError,
    UnsupportedPlatformError,
    make_runner_batch,
    normalize_bundle_root,
    resolve_bundle,
    validate_port,
    validate_read_only_command,
)
from .pm3.bundle import (
    batch_quote as _batch_quote,
    make_runner_batch_trusted as _make_runner_batch_trusted,
    make_session_batch as _make_session_batch,
    validate_internal_command as _validate_internal_command,
)
from .pm3.commands import (
    mfu_page as _mfu_page,
    staged_name as _staged_name,
    validated_pages as _validated_pages,
)
from .pm3.protocol import (
    decode_output as _decode_output,
    infer_command_returncode as _infer_command_returncode,
    marker_completed as _marker_completed,
    strip_marker_lines as _strip_marker_lines,
)

__all__ = [
    "ALLOWED_COMMANDS",
    "BundleLayout",
    "BundleValidationError",
    "OperationCancelledError",
    "PM3_PIPE_SAFE_COMMAND_LENGTH",
    "ProxmarkError",
    "ProxmarkRunner",
    "ProxmarkWriteRunner",
    "UnsafeCommandError",
    "UnsupportedPlatformError",
    "make_runner_batch",
    "normalize_bundle_root",
    "resolve_bundle",
    "validate_port",
    "validate_read_only_command",
]
