from __future__ import annotations

from ..i18n import Translator, normalize_locale
from .models import Type2Tlv


def parse_type2_tlvs(data: bytes, locale: str = "en") -> list[Type2Tlv]:
    """Parse NFC Forum Type 2 TLVs and retain their exact raw bytes."""
    t = Translator(normalize_locale(locale)).t
    records: list[Type2Tlv] = []
    cursor = 0
    while cursor < len(data):
        start = cursor
        tlv_type = data[cursor]
        cursor += 1
        if tlv_type == 0x00:
            records.append(
                Type2Tlv(tlv_type, start, cursor, b"", data[start:cursor])
            )
            continue
        if tlv_type == 0xFE:
            records.append(
                Type2Tlv(tlv_type, start, cursor, b"", data[start:cursor])
            )
            break
        if cursor >= len(data):
            raise ValueError(t("ndef.incomplete_tlv_length"))
        length = data[cursor]
        cursor += 1
        extended = False
        if length == 0xFF:
            extended = True
            if cursor + 2 > len(data):
                raise ValueError(t("ndef.incomplete_extended_tlv_length"))
            length = int.from_bytes(data[cursor : cursor + 2], "big")
            cursor += 2
        end = cursor + length
        if end > len(data):
            raise ValueError(t("ndef.tlv_out_of_bounds"))
        records.append(
            Type2Tlv(
                tlv_type=tlv_type,
                offset=start,
                end=end,
                value=data[cursor:end],
                raw=data[start:end],
                extended_length=extended,
            )
        )
        cursor = end
    return records


def extract_ndef_tlv(data: bytes, locale: str = "en") -> bytes | None:
    """Return the first NDEF TLV payload, or ``None`` when no NDEF exists."""
    for record in parse_type2_tlvs(data, locale):
        if record.tlv_type == 0x03:
            return record.value
        if record.tlv_type == 0xFE:
            break
    return None


def clear_ndef_tlv_area(data: bytes, locale: str = "en") -> tuple[bytes, bool]:
    """Empty NDEF TLVs in place without moving any following TLV records.

    The TLV type and starting offset remain unchanged. The length becomes zero,
    while bytes formerly occupied by an extended length and payload become NULL
    TLVs. Proprietary, lock-control, memory-control, terminator, and unknown
    records therefore remain byte-for-byte at their original addresses.
    """
    records = parse_type2_tlvs(data, locale)
    ndef_records = [record for record in records if record.tlv_type == 0x03]
    if not ndef_records:
        return data, False

    output = bytearray(data)
    for record in ndef_records:
        output[record.offset + 1] = 0x00
        output[record.offset + 2 : record.end] = b"\x00" * max(
            0, record.end - (record.offset + 2)
        )
    return bytes(output), True
