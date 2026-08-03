from __future__ import annotations

from dataclasses import dataclass

from ..nfc_type2.models import NdefRecord


@dataclass(frozen=True, slots=True)
class NdefReadResult:
    """Decoded read-only NFC Type 2 / NDEF result shown by the GUI."""

    uid: str
    profile_name: str
    records: tuple[NdefRecord, ...]
    message_bytes: bytes | None

    @property
    def has_ndef(self) -> bool:
        return self.message_bytes is not None
