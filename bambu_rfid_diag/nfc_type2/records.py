from __future__ import annotations

from ..i18n import Translator, normalize_locale
from .models import NdefRecord


def parse_ndef_message(data: bytes, locale: str = "en") -> list[NdefRecord]:
    """Parse a complete, non-chunked NDEF message."""
    t = Translator(normalize_locale(locale)).t
    records: list[NdefRecord] = []
    cursor = 0
    while cursor < len(data):
        header = data[cursor]
        cursor += 1
        message_begin = bool(header & 0x80)
        message_end = bool(header & 0x40)
        chunked = bool(header & 0x20)
        short_record = bool(header & 0x10)
        has_identifier = bool(header & 0x08)
        tnf = header & 0x07
        if chunked:
            raise ValueError(t("ndef.chunked_not_supported"))
        if cursor >= len(data):
            raise ValueError(t("ndef.incomplete_record"))

        type_length = data[cursor]
        cursor += 1
        if short_record:
            if cursor >= len(data):
                raise ValueError(t("ndef.missing_payload_length"))
            payload_length = data[cursor]
            cursor += 1
        else:
            if cursor + 4 > len(data):
                raise ValueError(t("ndef.missing_long_payload_length"))
            payload_length = int.from_bytes(data[cursor : cursor + 4], "big")
            cursor += 4

        identifier_length = 0
        if has_identifier:
            if cursor >= len(data):
                raise ValueError(t("ndef.missing_identifier_length"))
            identifier_length = data[cursor]
            cursor += 1

        record_end = cursor + type_length + identifier_length + payload_length
        if record_end > len(data):
            raise ValueError(t("ndef.record_out_of_bounds"))
        record_type = data[cursor : cursor + type_length]
        cursor += type_length
        identifier = data[cursor : cursor + identifier_length]
        cursor += identifier_length
        payload = data[cursor : cursor + payload_length]
        cursor += payload_length
        records.append(
            NdefRecord(
                tnf=tnf,
                type=record_type,
                payload=payload,
                identifier=identifier,
                message_begin=message_begin,
                message_end=message_end,
            )
        )
        if message_end:
            if cursor != len(data):
                raise ValueError(t("ndef.trailing_data"))
            break

    if not records or not records[0].message_begin or not records[-1].message_end:
        raise ValueError(t("ndef.invalid_message_flags"))
    return records
