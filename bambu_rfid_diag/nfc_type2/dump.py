from __future__ import annotations

from ..i18n import Translator, normalize_locale
from ..type2 import generic_profile_from_cc, profile_from_max_page
from .models import MfuDump
from .tlv import extract_ndef_tlv


MFU_HEADER_SIZE = 56


def parse_mfu_dump(data: bytes, locale: str = "en") -> MfuDump:
    """Parse a Proxmark MFU binary dump and derive known protection fields."""
    t = Translator(normalize_locale(locale)).t
    if len(data) < MFU_HEADER_SIZE + 16:
        raise ValueError(t("ndef.dump_too_short"))

    header = data[:MFU_HEADER_SIZE]
    max_page = header[11]
    expected_size = MFU_HEADER_SIZE + (max_page + 1) * 4
    if len(data) != expected_size:
        raise ValueError(
            t(
                "ndef.dump_size_mismatch",
                bytes=len(data),
                max_page=max_page,
                expected=expected_size,
            )
        )

    pages = data[MFU_HEADER_SIZE:]
    uid = pages[0:3] + pages[4:8]
    static_lock = pages[10:12]
    capability_container = pages[12:16]
    profile = profile_from_max_page(max_page) or generic_profile_from_cc(
        capability_container, max_page
    )

    dynamic_lock = None
    auth0 = None
    if (
        profile is not None
        and profile.dynamic_lock_page is not None
        and profile.config_page is not None
    ):
        dynamic_offset = profile.dynamic_lock_page * 4
        config_offset = profile.config_page * 4
        if config_offset + 4 <= len(pages):
            dynamic_lock = pages[dynamic_offset : dynamic_offset + 3]
            auth0 = pages[config_offset + 3]

    user_capacity = (
        capability_container[2] * 8
        if len(capability_container) == 4
        and capability_container[0] in {0xE1, 0xF1}
        else 0
    )
    user_area = pages[16 : 16 + user_capacity]
    ndef_message = extract_ndef_tlv(user_area, locale) if user_area else None

    return MfuDump(
        header=header,
        pages=pages,
        max_page=max_page,
        uid=uid,
        static_lock=static_lock,
        dynamic_lock=dynamic_lock,
        auth0=auth0,
        capability_container=capability_container,
        ndef_message=ndef_message,
        profile=profile,
    )
