from __future__ import annotations

import re

from ..i18n import Translator, normalize_locale
from ..domain import TagInfo
from .text import clean_output, first_hex_field


NO_TAG_MARKERS = (
    "no tag found",
    "no card found",
    "no known/supported 13.56 mhz tags found",
    "card not found",
    "select card failed",
    "can't select card",
    "couldn't identify a 13.56 mhz tag",
)


def parse_iso14a(text: str, locale: str = "en") -> TagInfo:
    """Parse ISO14443-A identity and perform conservative family detection."""
    tr = Translator(normalize_locale(locale))
    text = clean_output(text)
    lower = text.lower()
    uid = first_hex_field(text, "UID", 4, 10)
    atqa = first_hex_field(text, "ATQA", 2, 2)
    sak = first_hex_field(text, "SAK", 1, 1)

    possible_types: list[str] = []
    for match in re.finditer(
        r"(?im)^.*?(?:POSSIBLE TYPE|TYPE)\s*:\s*(.+?)\s*$", text
    ):
        value = match.group(1).strip()
        if value and value not in possible_types:
            possible_types.append(value)

    no_tag = any(marker in lower for marker in NO_TAG_MARKERS)
    present = bool(uid and not no_tag)
    family = "unknown"
    display_type = tr.t("parser.unknown_iso") if present else tr.t("parser.no_tag")

    if present:
        compact_atqa = (atqa or "").replace(" ", "")
        compact_sak = (sak or "").replace(" ", "")
        if "ntag 215" in lower or "ntag215" in lower:
            family = "ntag215"
            display_type = "NTAG215"
        elif "mifare classic 1k" in lower or (
            compact_atqa == "0004" and compact_sak == "08"
        ):
            family = "mfc1k"
            display_type = "MIFARE Classic 1K"
        elif (
            "mifare ultralight" in lower
            or "ntag" in lower
            or compact_sak == "00"
        ):
            family = "type2"
            display_type = tr.t("parser.type2")

    return TagInfo(
        present=present,
        uid=uid,
        atqa=atqa,
        sak=sak,
        family=family,
        display_type=display_type,
        possible_types=possible_types,
    )
