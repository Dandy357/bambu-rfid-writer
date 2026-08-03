from __future__ import annotations

from enum import StrEnum


class OperationKind(StrEnum):
    """Stable internal identifiers for persisted operation reports."""

    MFC_CLONE = "mfc_clone"
    TYPE2_NDEF_WRITE = "type2_ndef_write"
    TYPE2_NDEF_CLEAR = "type2_ndef_clear"
    TYPE2_USER_ZERO = "type2_user_zero"
