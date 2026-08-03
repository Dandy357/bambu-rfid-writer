"""Compatibility facade for report rendering, paths, and settings persistence."""

from .i18n import Translator
from .infrastructure.paths import (
    app_data_directory,
    diagnostic_log_directory as log_directory,
)
from .infrastructure.settings import (
    SettingsRepository,
    load_settings,
    save_settings,
    settings_path,
)
from .presentation.diagnostic_report import (
    OVERALL_KEYS as _OVERALL_KEYS,
    STATE_KEYS as _STATE_KEYS,
    format_report,
    overall_label,
    report_as_dict,
    save_report,
    state_label,
)

# Backward-compatible Czech labels retained for v0.5 callers and tests.
_cs = Translator("cs")
STATE_LABELS = {state: _cs.t(key) for state, key in _STATE_KEYS.items()}
OVERALL_LABELS = {state: _cs.t(key) for state, key in _OVERALL_KEYS.items()}

__all__ = [
    "OVERALL_LABELS",
    "STATE_LABELS",
    "SettingsRepository",
    "app_data_directory",
    "format_report",
    "load_settings",
    "log_directory",
    "overall_label",
    "report_as_dict",
    "save_report",
    "save_settings",
    "settings_path",
    "state_label",
]
