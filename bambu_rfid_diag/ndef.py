"""Compatibility facade for NFC Type 2 and NDEF helpers.

New code should import from :mod:`bambu_rfid_diag.nfc_type2`. This module keeps
v0.5 import paths stable for external callers and existing tests.
"""

from .nfc_type2 import (
    MFU_HEADER_SIZE,
    NTAG215_NDEF_CAPACITY,
    MfuDump,
    NdefRecord,
    NtagField,
    Type2Field,
    Type2Tlv,
    build_filament_ndef,
    build_ntag_ndef,
    build_type2_ndef,
    clear_ndef_tlv_area,
    extract_ndef_tlv,
    parse_mfu_dump,
    parse_ndef_message,
    parse_type2_tlvs,
)

# The historical private helper remains importable for integrations that used
# it, but new code should call ``extract_ndef_tlv``.
_extract_ndef_tlv = extract_ndef_tlv

__all__ = [
    "MFU_HEADER_SIZE",
    "NTAG215_NDEF_CAPACITY",
    "MfuDump",
    "NdefRecord",
    "NtagField",
    "Type2Field",
    "Type2Tlv",
    "build_filament_ndef",
    "build_ntag_ndef",
    "build_type2_ndef",
    "clear_ndef_tlv_area",
    "extract_ndef_tlv",
    "parse_mfu_dump",
    "parse_ndef_message",
    "parse_type2_tlvs",
]
