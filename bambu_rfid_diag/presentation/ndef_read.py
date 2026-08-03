from __future__ import annotations

from ..domain import NdefReadResult
from ..i18n import Translator, normalize_locale


def format_ndef_read_result(result: NdefReadResult, locale: str = "en") -> str:
    """Format decoded NDEF records for a copyable result dialog."""

    t = Translator(normalize_locale(locale)).t
    lines = [
        t("reader.result_uid", uid=result.uid),
        t("reader.result_profile", profile=result.profile_name),
        "",
    ]
    if not result.has_ndef:
        lines.append(t("reader.no_ndef_content"))
        return "\n".join(lines)

    lines.append(t("reader.result_heading"))
    for index, record in enumerate(result.records, start=1):
        decoded = record.decoded_value()
        if record.tnf == 1 and record.type == b"U" and decoded is not None:
            label = t("reader.record_url")
            value = decoded
        elif record.tnf == 1 and record.type == b"T" and decoded is not None:
            label = t("reader.record_text")
            value = decoded
        else:
            label = t(
                "reader.record_unknown",
                tnf=record.tnf,
                type=(
                    record.type.decode("ascii", errors="replace")
                    if record.type
                    else "—"
                ),
            )
            value = record.payload.hex(" ").upper() or t("reader.empty_payload")
        lines.append(t("reader.record_line", index=index, label=label))
        value_lines = value.splitlines() or [""]
        lines.extend(f"    {line}" for line in value_lines)
    return "\n".join(lines)
