from __future__ import annotations

from dataclasses import dataclass


PROFILE_AUTO = "auto"
PROFILE_GENERIC = "type2_generic"
PROFILE_NTAG213 = "ntag213"
PROFILE_NTAG215 = "ntag215"
PROFILE_NTAG216 = "ntag216"


@dataclass(frozen=True, slots=True)
class Type2Profile:
    identifier: str
    display_name: str
    vendor: str | None
    max_page: int | None
    user_first_page: int
    user_last_page: int | None
    ndef_capacity: int
    ndef_first_page: int = 4
    dynamic_lock_page: int | None = None
    config_page: int | None = None
    supports_originality: bool = False
    known_layout: bool = True

    @property
    def ndef_last_page(self) -> int:
        pages = (self.ndef_capacity + 3) // 4
        return self.ndef_first_page + pages - 1


NTAG213 = Type2Profile(
    identifier=PROFILE_NTAG213,
    display_name="NXP NTAG213",
    vendor="NXP",
    max_page=44,
    user_first_page=4,
    user_last_page=39,
    ndef_capacity=144,
    dynamic_lock_page=40,
    config_page=41,
    supports_originality=True,
)
NTAG215 = Type2Profile(
    identifier=PROFILE_NTAG215,
    display_name="NXP NTAG215",
    vendor="NXP",
    max_page=134,
    user_first_page=4,
    user_last_page=129,
    ndef_capacity=496,
    dynamic_lock_page=130,
    config_page=131,
    supports_originality=True,
)
NTAG216 = Type2Profile(
    identifier=PROFILE_NTAG216,
    display_name="NXP NTAG216",
    vendor="NXP",
    max_page=230,
    user_first_page=4,
    user_last_page=225,
    ndef_capacity=872,
    dynamic_lock_page=226,
    config_page=227,
    supports_originality=True,
)

KNOWN_PROFILES = {
    profile.identifier: profile for profile in (NTAG213, NTAG215, NTAG216)
}
MAX_KNOWN_NDEF_CAPACITY = max(profile.ndef_capacity for profile in KNOWN_PROFILES.values())


def profile_from_identifier(identifier: str | None) -> Type2Profile | None:
    return KNOWN_PROFILES.get((identifier or "").strip().lower())


def profile_from_max_page(max_page: int) -> Type2Profile | None:
    for profile in KNOWN_PROFILES.values():
        if profile.max_page == max_page:
            return profile
    return None


def profile_from_text(text: str) -> Type2Profile | None:
    lower = text.lower().replace(" ", "")
    if "ntag213" in lower:
        return NTAG213
    if "ntag215" in lower:
        return NTAG215
    if "ntag216" in lower:
        return NTAG216
    return None


def generic_profile_from_cc(cc: bytes, max_page: int | None = None) -> Type2Profile | None:
    if len(cc) != 4 or cc[0] not in {0xE1, 0xF1}:
        return None
    capacity = cc[2] * 8
    if capacity <= 0:
        return None
    ndef_pages = (capacity + 3) // 4
    safe_last = 4 + ndef_pages - 1
    if max_page is not None:
        safe_last = min(safe_last, max_page)
        capacity = max(0, (safe_last - 4 + 1) * 4)
    return Type2Profile(
        identifier=PROFILE_GENERIC,
        display_name="NFC Forum Type 2",
        vendor=None,
        max_page=max_page,
        user_first_page=4,
        user_last_page=safe_last,
        ndef_capacity=capacity,
        dynamic_lock_page=None,
        config_page=None,
        supports_originality=False,
        known_layout=False,
    )
