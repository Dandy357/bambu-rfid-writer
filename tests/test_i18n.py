from __future__ import annotations

import json
import string
import unittest
from pathlib import Path

from bambu_rfid_diag.i18n import DEFAULT_LOCALE, Translator, available_locales
from bambu_rfid_diag.models import CheckItem, CheckState, DiagnosticReport, HardwareInfo, OverallState, TagInfo
from bambu_rfid_diag.parsers import enrich_mfu_info, parse_iso14a
from bambu_rfid_diag.reporting import format_report


class I18nTests(unittest.TestCase):
    def test_czech_and_english_catalogs_have_identical_keys(self):
        root = Path(__file__).resolve().parents[1] / "bambu_rfid_diag" / "locales"
        cs = json.loads((root / "cs.json").read_text(encoding="utf-8"))
        en = json.loads((root / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(set(cs), set(en))
        formatter = string.Formatter()
        for key in cs:
            cs_fields = {field for _literal, field, _spec, _conversion in formatter.parse(cs[key]) if field}
            en_fields = {field for _literal, field, _spec, _conversion in formatter.parse(en[key]) if field}
            self.assertEqual(cs_fields, en_fields, key)
        self.assertIn("cs", available_locales())
        self.assertIn("en", available_locales())
        self.assertEqual(next(iter(cs)), "language.name")
        self.assertEqual(next(iter(en)), "language.name")

    def test_clean_install_default_locale_is_english(self):
        self.assertEqual(DEFAULT_LOCALE, "en")
        self.assertEqual(Translator().locale, "en")
        self.assertEqual(available_locales()[0], "en")

    def test_english_parser_messages_are_localized(self):
        tag = parse_iso14a("[-] No known/supported 13.56 MHz tags found", "en")
        self.assertEqual(tag.display_type, "No tag is present")

        tag = TagInfo(present=True, family="ntag215", auth0="FF", static_lock="00 00", dynamic_lock="00 00 00")
        enrich_mfu_info(tag, "NTAG 215", "en")
        self.assertIn("AUTH0 is disabled", tag.readiness_detail or "")
        self.assertNotIn("rozpozn", tag.readiness_detail or "")

    def test_english_report_uses_english_headings(self):
        report = DiagnosticReport(
            started_at_iso="2026-08-02T18:00:00+02:00",
            finished_at_iso="2026-08-02T18:00:01+02:00",
            bundle_root=Path("C:/pm3"),
            requested_port=None,
            overall_state=OverallState.NO_TAG,
            summary="No tag is present.",
            hardware=HardwareInfo(),
            tag=TagInfo(),
            checks=[CheckItem("Attached tag", CheckState.INFO, "No tag is present.")],
            locale="en",
        )
        text = format_report(report, "en")
        self.assertIn("OVERALL RESULT", text)
        self.assertIn("CHECKS", text)
        self.assertNotIn(Translator("cs").t("report.overall"), text)

    def test_source_status_accepts_key_filename_placeholder(self):
        text = Translator("cs").t(
            "app.source_valid",
            label="PETG / PETG Basic / Black / A1B2C3D4",
            uid="A1B2C3D4",
            dump="hf-mf-A1B2C3D4-dump.bin",
            key_file="hf-mf-A1B2C3D4-key.bin",
            sha="0123456789ABCDEF",
        )
        self.assertIn("hf-mf-A1B2C3D4-key.bin", text)

    def test_example_auto_detection_text_is_impersonal(self):
        cs = Translator("cs")
        text = cs.t("diag.communication_auto", port="COM8")
        self.assertIn("COM8", text)
        self.assertEqual(text, cs.catalog["diag.communication_auto"].format(port="COM8"))


if __name__ == "__main__":
    unittest.main()
