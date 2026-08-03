"""Compatibility facade for protocol-specific Proxmark parsers.

New code should import from :mod:`bambu_rfid_diag.pm3_parsing` or one of its
protocol modules. The former flat API remains available for v0.5 callers.
"""

from .pm3_parsing import (
    ANSI_RE,
    DefaultKeyCheck,
    NO_TAG_MARKERS,
    clean_output,
    enrich_mfu_info,
    enrich_mifare_info,
    parse_default_key_check,
    parse_default_key_details,
    parse_hardware,
    parse_iso14a,
)

__all__ = [
    "ANSI_RE",
    "DefaultKeyCheck",
    "NO_TAG_MARKERS",
    "clean_output",
    "enrich_mfu_info",
    "enrich_mifare_info",
    "parse_default_key_check",
    "parse_default_key_details",
    "parse_hardware",
    "parse_iso14a",
]
