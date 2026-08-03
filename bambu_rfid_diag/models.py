"""Compatibility facade for application domain models.

New code should import models from :mod:`bambu_rfid_diag.domain`. The flat v0.5
module remains available for external integrations and existing tests.
"""

from .domain.checks import CheckItem, CheckState, OverallState
from .domain.commands import CommandResult
from .domain.diagnostic_reports import DiagnosticReport
from .domain.hardware import HardwareInfo
from .domain.tags import TagFamily, TagInfo

from .version import APP_NAME, APP_VERSION

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "CheckItem",
    "CheckState",
    "CommandResult",
    "DiagnosticReport",
    "HardwareInfo",
    "OverallState",
    "TagFamily",
    "TagInfo",
]
