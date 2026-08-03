from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TagFamily(str, Enum):
    """Stable protocol-family identifiers used by parsers and workflows."""

    UNKNOWN = "unknown"
    MIFARE_CLASSIC_1K = "mfc1k"
    TYPE2 = "type2"
    NTAG213 = "ntag213"
    NTAG215 = "ntag215"
    NTAG216 = "ntag216"


@dataclass(slots=True)
class TagInfo:
    """Compatibility view of parsed tag identity and protocol details.

    The current GUI and report format consume one combined model. Protocol
    parsers own disjoint field groups; new protocol-specific behavior should be
    implemented in the corresponding inspector rather than added to generic
    orchestration code.
    """

    present: bool = False
    uid: str | None = None
    atqa: str | None = None
    sak: str | None = None
    family: str = TagFamily.UNKNOWN.value
    display_type: str = "Unknown tag"
    possible_types: list[str] = field(default_factory=list)

    # MIFARE Classic details.
    magic_kind: str | None = None
    fingerprint: str | None = None
    prng: str | None = None
    default_keys: bool | None = None
    default_key_sectors_seen: int = 0

    # NFC Type 2 protection and profile details.
    auth0: str | None = None
    static_lock: str | None = None
    dynamic_lock: str | None = None
    originality_signature: str | None = None
    originality_verified: bool | None = None
    declared_vendor: str | None = None
    type2_profile: str | None = None
    total_pages: int | None = None
    user_first_page: int | None = None
    user_last_page: int | None = None
    ndef_capacity: int | None = None
    dynamic_lock_page: int | None = None
    config_page: int | None = None

    # Shared readiness assessment produced by a protocol-specific inspector.
    future_write_ready: bool | None = None
    readiness_detail: str | None = None
