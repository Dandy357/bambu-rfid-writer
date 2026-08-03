from __future__ import annotations

import re

from ..i18n import Translator, normalize_locale
from ..domain import TagInfo
from ..type2 import generic_profile_from_cc, profile_from_text
from .text import clean_output, config_hex_line, first_hex_field


def enrich_mfu_info(tag: TagInfo, text: str, locale: str = "en") -> TagInfo:
    """Add NFC Type 2 profile, lock, authentication, and signature details."""
    tr = Translator(normalize_locale(locale))
    text = clean_output(text)
    lower = text.lower()
    profile = profile_from_text(text)
    if profile is None:
        cc_match = re.search(
            r"(?im)Capability Container\s*:\s*([0-9A-Fa-f]{8})", text
        )
        if cc_match:
            try:
                profile = generic_profile_from_cc(bytes.fromhex(cc_match.group(1)))
            except ValueError:
                profile = None
    if profile is not None:
        tag.family = profile.identifier
        tag.display_type = profile.display_name
        tag.type2_profile = profile.identifier
        tag.declared_vendor = profile.vendor
        tag.total_pages = (
            profile.max_page + 1 if profile.max_page is not None else None
        )
        tag.user_first_page = profile.user_first_page
        tag.user_last_page = profile.user_last_page
        tag.ndef_capacity = profile.ndef_capacity
        tag.dynamic_lock_page = profile.dynamic_lock_page
        tag.config_page = profile.config_page
    elif tag.family == "unknown" and (
        "ntag" in lower or "ultralight" in lower or "type 2" in lower
    ):
        tag.family = "type2"
        tag.display_type = tr.t("parser.type2")

    if not tag.uid:
        tag.uid = first_hex_field(text, "UID", 4, 10)

    auth0_match = re.search(
        r"(?im)^.*?\bAUTH0\b.*?:\s*(?:0x)?([0-9A-Fa-f]{2})\b", text
    )
    if auth0_match:
        tag.auth0 = auth0_match.group(1).upper()

    cfg0_match = re.search(
        r"(?im)^.*?\bcfg0\s*\[\s*\d+\s*/\s*0x[0-9A-Fa-f]+\s*\]\s*:\s*"
        r"((?:[0-9A-Fa-f]{2}\s+){3}[0-9A-Fa-f]{2})",
        text,
    )
    if cfg0_match:
        cfg0 = re.findall(r"[0-9A-Fa-f]{2}", cfg0_match.group(1))
        if len(cfg0) == 4:
            tag.auth0 = cfg0[3].upper()

    def read_page(page: int, hex_page: str) -> str | None:
        match = re.search(
            rf"(?im)^.*?\b{page}\s*(?:/\s*0x{hex_page})?\s*\|\s*"
            r"((?:[0-9A-Fa-f]{2}\s+){3}[0-9A-Fa-f]{2})\s*\|",
            text,
        )
        if not match:
            return None
        values = re.findall(r"[0-9A-Fa-f]{2}", match.group(1))
        return " ".join(value.upper() for value in values)

    if tag.dynamic_lock_page is not None:
        dynamic_page = read_page(
            tag.dynamic_lock_page, f"{tag.dynamic_lock_page:02X}"
        )
        if dynamic_page:
            tag.dynamic_lock = " ".join(dynamic_page.split()[:3])
    if tag.config_page is not None:
        config_page = read_page(tag.config_page, f"{tag.config_page:02X}")
        if config_page and len(config_page.split()) == 4:
            tag.auth0 = config_page.split()[3]

    tag.dynamic_lock = config_hex_line(
        text, r"\bdynamic\s+lock\b", (3, 3)
    ) or tag.dynamic_lock
    tag.static_lock = config_hex_line(
        text, r"(?<!dynamic\s)\b(?:static\s+)?lock\b", (2, 2)
    ) or tag.static_lock

    signature_bytes: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "tag ic signature" not in line.lower():
            continue
        for signature_line in lines[index : index + 3]:
            tail = (
                signature_line.split(":", 1)[1]
                if ":" in signature_line
                else ""
            )
            values = re.findall(r"[0-9A-Fa-f]{2}", tail)
            if not values:
                if signature_line is not line:
                    break
                continue
            signature_bytes.extend(values)
            if len(signature_bytes) >= 32:
                break
        break
    if len(signature_bytes) >= 32:
        tag.originality_signature = "".join(
            value.upper() for value in signature_bytes[:32]
        )

    verification_match = re.search(
        r"(?im)^.*?Signature verification\s*:\s*(.+?)\s*$", text
    )
    if verification_match:
        verification = verification_match.group(1).strip().lower()
        if any(word in verification for word in ("failed", "invalid", "not valid")):
            tag.originality_verified = False
        elif any(
            word in verification
            for word in ("successful", "verified", "valid", "ok")
        ):
            tag.originality_verified = True
    elif tag.originality_signature == "0" * 64:
        tag.originality_verified = False

    if tag.type2_profile in {"ntag213", "ntag215", "ntag216"}:
        lock_values_known = (
            tag.static_lock is not None and tag.dynamic_lock is not None
        )
        locks_clear = lock_values_known and all(
            byte == "00"
            for byte in (tag.static_lock + " " + tag.dynamic_lock).split()
        )
        if tag.auth0 == "FF" and locks_clear:
            tag.future_write_ready = True
            tag.readiness_detail = tr.t("parser.ntag_ready")
        elif tag.auth0 is not None and tag.auth0 != "FF":
            tag.future_write_ready = False
            tag.readiness_detail = tr.t("parser.auth_active", auth0=tag.auth0)
        elif lock_values_known and not locks_clear:
            tag.future_write_ready = False
            tag.readiness_detail = tr.t("parser.locks_active")
        else:
            tag.future_write_ready = None
            tag.readiness_detail = tr.t("parser.protection_unknown")

    return tag
