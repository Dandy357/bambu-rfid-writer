from __future__ import annotations

from dataclasses import dataclass

from ..type2 import Type2Profile


URI_PREFIXES = {
    0x00: "",
    0x01: "http://www.",
    0x02: "https://www.",
    0x03: "http://",
    0x04: "https://",
    0x05: "tel:",
    0x06: "mailto:",
}


@dataclass(frozen=True, slots=True)
class MfuDump:
    """Parsed Proxmark MFU binary dump and derived Type 2 metadata."""

    header: bytes
    pages: bytes
    max_page: int
    uid: bytes
    static_lock: bytes
    dynamic_lock: bytes | None
    auth0: int | None
    capability_container: bytes
    ndef_message: bytes | None
    profile: Type2Profile | None


@dataclass(frozen=True, slots=True)
class NdefRecord:
    """One decoded NDEF record with its original protocol flags."""

    tnf: int
    type: bytes
    payload: bytes
    identifier: bytes
    message_begin: bool
    message_end: bool

    def decoded_value(self) -> str | None:
        """Decode supported well-known URI and text records."""
        if self.tnf == 1 and self.type == b"U" and self.payload:
            prefix = URI_PREFIXES.get(self.payload[0])
            if prefix is None:
                return None
            return prefix + self.payload[1:].decode("utf-8", errors="strict")
        if self.tnf == 1 and self.type == b"T" and self.payload:
            status = self.payload[0]
            language_length = status & 0x3F
            encoding = "utf-16" if status & 0x80 else "utf-8"
            start = 1 + language_length
            if start > len(self.payload):
                return None
            return self.payload[start:].decode(encoding, errors="strict")
        return None


@dataclass(frozen=True, slots=True)
class Type2Tlv:
    """One Type-Length-Value item with exact source offsets and bytes."""

    tlv_type: int
    offset: int
    end: int
    value: bytes
    raw: bytes
    extended_length: bool = False


@dataclass(frozen=True, slots=True)
class Type2Field:
    """One logical field in the exact order shown by the GUI."""

    name: str
    value: str
    write_name: bool = False
    kind: str = "text"


# Compatibility alias retained for v0.5 callers and saved integrations.
NtagField = Type2Field
