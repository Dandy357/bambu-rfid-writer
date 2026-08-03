from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from ..i18n import Translator, normalize_locale
from .models import URI_PREFIXES, Type2Field


NTAG215_NDEF_CAPACITY = 496


def build_filament_ndef(
    brand: str,
    filament_type: str,
    purchase_date: str,
    url: str,
    language: str = "en",
    locale: str = "en",
    capacity: int = NTAG215_NDEF_CAPACITY,
) -> bytes:
    """Build the backward-compatible v0.2 filament NDEF template."""
    t = Translator(normalize_locale(locale)).t
    fields = {
        t("ndef.field_brand"): brand.strip(),
        t("ndef.field_filament"): filament_type.strip(),
        t("ndef.field_date"): purchase_date.strip(),
        t("ndef.field_url"): url.strip(),
    }
    _validate_values(fields, t)
    _validate_url(fields[t("ndef.field_url")], t)

    uri_payload = _uri_payload(fields[t("ndef.field_url")])
    language_bytes = _language_bytes(language, t)
    text = (
        f"{fields[t('ndef.field_brand')]}\n"
        f"{fields[t('ndef.field_filament')]}\n"
        f"{t('ndef.purchased_label', date=fields[t('ndef.field_date')])}"
    )
    text_payload = bytes([len(language_bytes)]) + language_bytes + text.encode(
        "utf-8"
    )
    ndef = _encode_record(0x91, b"U", uri_payload, t) + _encode_record(
        0x51, b"T", text_payload, t
    )
    return _wrap_tlv(ndef, t, capacity)


def build_type2_ndef(
    fields: list[Type2Field],
    language: str = "en",
    locale: str = "en",
    capacity: int = NTAG215_NDEF_CAPACITY,
) -> bytes:
    """Build an NDEF message that preserves the exact GUI field order.

    Consecutive text fields are compacted into one Text record. A URI field is
    emitted at its position in the list, so text may appear before or after the
    clickable link. Text-only and URI-only messages are both valid. At most one
    URI field is supported by the editor.
    """
    t = Translator(normalize_locale(locale)).t
    if not fields:
        raise ValueError(t("ndef.no_fields"))

    normalized: list[Type2Field] = []
    for field in fields:
        name = field.name.strip()
        value = field.value.strip()
        kind = field.kind.strip().lower()
        if kind not in {"text", "uri"}:
            raise ValueError(t("ndef.invalid_field_kind", kind=field.kind))
        if not name:
            raise ValueError(t("ndef.empty_field_name"))
        if not value:
            raise ValueError(t("ndef.empty_field_value", field=name))
        if len(name) > 80:
            raise ValueError(t("ndef.field_name_too_long", field=name))
        normalized.append(
            Type2Field(
                name=name,
                value=value,
                write_name=field.write_name,
                kind=kind,
            )
        )

    values = {field.name: field.value for field in normalized}
    _validate_values(values, t)
    uri_fields = [field for field in normalized if field.kind == "uri"]
    if len(uri_fields) > 1:
        raise ValueError(t("ndef.multiple_urls_not_supported"))
    if uri_fields:
        _validate_url(uri_fields[0].value, t)

    language_bytes = _language_bytes(language, t)
    records: list[tuple[bytes, bytes]] = []
    text_lines: list[str] = []

    def flush_text() -> None:
        if not text_lines:
            return
        payload = (
            bytes([len(language_bytes)])
            + language_bytes
            + "\n".join(text_lines).encode("utf-8")
        )
        records.append((b"T", payload))
        text_lines.clear()

    for field in normalized:
        if field.kind == "uri":
            flush_text()
            records.append((b"U", _uri_payload(field.value)))
        else:
            text_lines.append(
                f"{field.name} {field.value}" if field.write_name else field.value
            )
    flush_text()

    ndef = bytearray()
    for index, (record_type, payload) in enumerate(records):
        header = 0x01
        if index == 0:
            header |= 0x80
        if index == len(records) - 1:
            header |= 0x40
        ndef.extend(_encode_record(header, record_type, payload, t))
    return _wrap_tlv(bytes(ndef), t, capacity)


def build_ntag_ndef(
    fields: list[Type2Field],
    language: str = "en",
    locale: str = "en",
    capacity: int = NTAG215_NDEF_CAPACITY,
) -> bytes:
    """Compatibility wrapper for the former NTAG-specific public name."""
    return build_type2_ndef(fields, language, locale, capacity)


def _validate_values(fields: dict[str, str], t: Callable[..., str]) -> None:
    empty = [name for name, value in fields.items() if not value]
    if empty:
        raise ValueError(t("ndef.empty_fields", fields=", ".join(empty)))
    if any(
        any(ord(character) < 0x20 for character in name + value)
        for name, value in fields.items()
    ):
        raise ValueError(t("ndef.control_chars"))


def _validate_url(url: str, t: Callable[..., str]) -> None:
    parsed_url = urlsplit(url)
    if parsed_url.scheme.lower() not in {"https", "http"}:
        raise ValueError(t("ndef.url_scheme"))
    if not parsed_url.netloc:
        raise ValueError(t("ndef.url_incomplete"))


def _language_bytes(language: str, t: Callable[..., str]) -> bytes:
    try:
        language_bytes = language.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(t("ndef.language_ascii")) from exc
    if len(language_bytes) > 63:
        raise ValueError(t("ndef.language_too_long"))
    return language_bytes


def _uri_payload(url: str) -> bytes:
    uri_code, uri_remainder = _compress_uri(url)
    return bytes([uri_code]) + uri_remainder.encode("utf-8")


def _wrap_tlv(
    ndef: bytes,
    t: Callable[..., str],
    capacity: int = NTAG215_NDEF_CAPACITY,
) -> bytes:
    if len(ndef) <= 0xFE:
        tlv_length = bytes([len(ndef)])
    elif len(ndef) <= 0xFFFF:
        tlv_length = b"\xFF" + len(ndef).to_bytes(2, "big")
    else:
        raise ValueError(t("ndef.message_too_long"))
    result = b"\x03" + tlv_length + ndef + b"\xFE"
    if capacity <= 0:
        raise ValueError(t("ndef.capacity_exceeded", bytes=len(result)))
    if len(result) > capacity:
        raise ValueError(t("ndef.capacity_exceeded", bytes=len(result) - capacity))
    return result


def _compress_uri(url: str) -> tuple[int, str]:
    choices = sorted(
        URI_PREFIXES.items(), key=lambda item: len(item[1]), reverse=True
    )
    for code, prefix in choices:
        if prefix and url.lower().startswith(prefix):
            return code, url[len(prefix) :]
    return 0x00, url


def _encode_record(
    header: int,
    record_type: bytes,
    payload: bytes,
    t: Callable[..., str] | None = None,
) -> bytes:
    if len(record_type) > 0xFF:
        if t is None:
            t = Translator("en").t
        raise ValueError(t("ndef.record_type_too_long"))
    if len(payload) <= 0xFF:
        header |= 0x10
        encoded_length = bytes([len(payload)])
    else:
        header &= ~0x10
        encoded_length = len(payload).to_bytes(4, "big")
    return bytes([header, len(record_type)]) + encoded_length + record_type + payload
