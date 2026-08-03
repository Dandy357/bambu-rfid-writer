from __future__ import annotations

from dataclasses import dataclass
import re

from ..i18n import Translator, normalize_locale
from ..domain import TagInfo
from .text import clean_output


KEY_ROW_RE = re.compile(
    r"(?m)^\s*(?:\[[^\]]+\]\s*)?\|?\s*(\d{1,3})\s*\|"
    r"(?:\s*\d{1,3}\s*\|)?\s*"
    r"([0-9A-Fa-f?-]{12})\s*\|\s*([01])\s*"
    r"\|\s*([0-9A-Fa-f?-]{12})\s*\|\s*([01])\s*(?:\||$)"
)


@dataclass(frozen=True, slots=True)
class DefaultKeyCheck:
    """Structured result of a 16-sector default-key table."""

    complete: bool
    sectors_seen: int
    successful_keys: int
    all_default: bool | None


def enrich_mifare_info(tag: TagInfo, text: str, locale: str = "en") -> TagInfo:
    """Add MIFARE Classic fingerprint, Magic, and PRNG details to a tag."""
    tr = Translator(normalize_locale(locale))
    text = clean_output(text)
    lower = text.lower()

    if tag.family == "unknown" and "mifare classic 1k" in lower:
        tag.family = "mfc1k"
        tag.display_type = "MIFARE Classic 1K"

    if "cuid" in lower and re.search(r"gen(?:eration)?\s*2", lower):
        tag.magic_kind = "CUID / Magic Gen2"
    elif re.search(r"gen(?:eration)?\s*1a", lower):
        tag.magic_kind = "Magic Gen1a"
    elif re.search(r"gen(?:eration)?\s*1b", lower):
        tag.magic_kind = "Magic Gen1b"
    elif re.search(r"gen(?:eration)?\s*4", lower):
        tag.magic_kind = "Magic Gen4"
    elif "magic" in lower:
        magic_line = next(
            (
                line.strip()
                for line in text.splitlines()
                if "magic" in line.lower()
            ),
            None,
        )
        tag.magic_kind = magic_line or tr.t("parser.magic_unknown")

    fingerprint_match = re.search(
        r"(?im)^.*?\bFingerprint\b\.*\s*:\s*(.+?)\s*$", text
    )
    if fingerprint_match:
        tag.fingerprint = fingerprint_match.group(1).strip()
    elif "fudan" in lower:
        tag.fingerprint = tr.t("parser.fudan")

    prng_match = re.search(
        r"(?im)^.*?PRNG(?:\s+detection)?\.*\s*:\s*(.+?)\s*$", text
    )
    if not prng_match:
        prng_match = re.search(
            r"(?im)^.*?PRNG\.*\s+(weak|hard|static|fixed).*$", text
        )
    if prng_match:
        tag.prng = prng_match.group(1).strip()
    elif "weak prng" in lower or "prng is weak" in lower:
        tag.prng = "weak"

    return tag


def parse_default_key_details(text: str) -> DefaultKeyCheck:
    """Parse all key A/B outcomes without confusing zero matches with failure."""
    text = clean_output(text)
    rows: dict[int, tuple[str, int, str, int]] = {}
    for match in KEY_ROW_RE.finditer(text):
        sector = int(match.group(1))
        if 0 <= sector <= 15:
            rows[sector] = (
                match.group(2).upper(),
                int(match.group(3)),
                match.group(4).upper(),
                int(match.group(5)),
            )
    successful = sum(
        result_a + result_b for _, result_a, _, result_b in rows.values()
    )
    complete = len(rows) == 16
    if complete:
        expected = "FFFFFFFFFFFF"
        all_default = all(
            key_a == expected
            and result_a == 1
            and key_b == expected
            and result_b == 1
            for key_a, result_a, key_b, result_b in rows.values()
        )
    elif "no valid key found" in text.lower() or "no keys found" in text.lower():
        all_default = False
    else:
        all_default = None
    return DefaultKeyCheck(complete, len(rows), successful, all_default)


def parse_default_key_check(text: str) -> tuple[bool | None, int]:
    details = parse_default_key_details(text)
    return details.all_default, details.sectors_seen
