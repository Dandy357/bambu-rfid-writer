from __future__ import annotations

import unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.diagnostics import DiagnosticService
from bambu_rfid_diag.models import CommandResult, OverallState
from bambu_rfid_diag.ui.option_state import OperationSettingsMixin
from bambu_rfid_diag.options import (
    PROFILE_FAST,
    PROFILE_RECOMMENDED,
    PROFILE_THOROUGH,
    TimeoutOptions,
    detect_profile,
    mfc_profile,
    ntag_erase_profile,
    ntag_write_profile,
    NTAG_METHOD_RESTORE,
)
from bambu_rfid_diag.proxmark import OperationCancelledError, _infer_command_returncode
from bambu_rfid_diag.reporting import format_report


class OptionAndSessionTests(unittest.TestCase):
    def test_fast_profiles_keep_minimum_tag_safety_checks(self) -> None:
        mfc = mfc_profile(PROFILE_FAST)
        self.assertTrue(mfc.tag_type)
        self.assertTrue(mfc.magic_type)
        self.assertTrue(mfc.default_keys)
        self.assertTrue(mfc.source.dump_size)
        self.assertTrue(mfc.source.key_size)
        self.assertTrue(mfc.source.bcc)
        self.assertTrue(mfc.source.trailer_keys)
        self.assertTrue(mfc.source.access_bits)
        self.assertTrue(mfc.source.filename_uid)
        self.assertFalse(mfc.client_firmware)
        self.assertFalse(mfc.backup)
        self.assertFalse(mfc.verify_dump)
        self.assertFalse(mfc.verify_uid)

        ntag = ntag_write_profile(PROFILE_FAST)
        self.assertTrue(ntag.tag_type)
        self.assertTrue(ntag.static_lock)
        self.assertTrue(ntag.dynamic_lock)
        self.assertTrue(ntag.auth0)
        self.assertFalse(ntag.client_firmware)
        self.assertFalse(ntag.backup)
        self.assertFalse(ntag.final_verify)

        erase = ntag_erase_profile(PROFILE_FAST)
        self.assertTrue(erase.tag_type)
        self.assertTrue(erase.static_lock)
        self.assertTrue(erase.dynamic_lock)
        self.assertTrue(erase.auth0)
        self.assertFalse(erase.client_firmware)
        self.assertFalse(erase.backup)
        self.assertFalse(erase.final_verify)

    def test_recommended_and_thorough_profiles_are_valid(self) -> None:
        self.assertEqual(mfc_profile(PROFILE_RECOMMENDED).profile, PROFILE_RECOMMENDED)
        self.assertEqual(mfc_profile(PROFILE_THOROUGH).profile, PROFILE_THOROUGH)
        self.assertTrue(mfc_profile(PROFILE_RECOMMENDED).client_firmware)
        self.assertTrue(ntag_write_profile(PROFILE_RECOMMENDED).client_firmware)
        self.assertTrue(ntag_erase_profile(PROFILE_RECOMMENDED).client_firmware)
        self.assertFalse(ntag_write_profile(PROFILE_RECOMMENDED).ecc_signature)
        self.assertTrue(ntag_write_profile(PROFILE_THOROUGH).ecc_signature)


    def test_custom_field_boolean_parsing_is_strict(self) -> None:
        parser = OperationSettingsMixin._strict_bool
        self.assertFalse(parser("false"))
        self.assertFalse(parser("0"))
        self.assertTrue(parser("true"))
        self.assertTrue(parser("1"))
        self.assertFalse(parser(False))
        self.assertTrue(parser(True))
        self.assertTrue(parser("unexpected", default=True))


    def test_method_mismatch_is_detected_as_custom_profile(self) -> None:
        value = ntag_write_profile(PROFILE_RECOMMENDED)
        value = type(value)(
            **{
                field.name: (
                    NTAG_METHOD_RESTORE
                    if field.name == "method"
                    else getattr(value, field.name)
                )
                for field in fields(value)
            }
        )
        self.assertEqual(
            detect_profile(value, ntag_write_profile),
            "custom",
        )

    def test_timeout_normalization_keeps_zero_and_clamps_negative_values(self) -> None:
        self.assertEqual(
            TimeoutOptions(-1, 0, 301, -9).normalized(),
            TimeoutOptions(0, 0, 301, 0),
        )

    def test_raw_client_failures_are_not_reported_as_success(self) -> None:
        for output in (
            "[!] Can't select card.",
            "[!] timeout while waiting for reply",
            "[!] Tag type not detected",
            "[!] command execution time out",
        ):
            with self.subTest(output=output):
                self.assertNotEqual(_infer_command_returncode(output), 0)

    def test_timeout_reason_is_written_to_diagnostic_report(self) -> None:
        command = CommandResult("hw version", -2, "partial", 91.0, True, "idle")
        report = SimpleNamespace(
            locale="en", started_at_iso="start", finished_at_iso="end", bundle_root=Path("C:/pm3"),
            requested_port=None, pm3_sessions=1, overall_state=OverallState.ERROR,
            summary="timeout", checks=[], commands=[command], hardware=SimpleNamespace(
                port=None, communication=None, mcu=None, memory=None, target=None, client_version=None,
                bootrom_version=None, os_version=None, version_match=None,
            ), tag=SimpleNamespace(
                present=False, display_type="Unknown", family="unknown", uid=None, atqa=None, sak=None,
                magic_kind=None, fingerprint=None, prng=None, default_keys=None, default_key_sectors_seen=0,
                auth0=None, static_lock=None, dynamic_lock=None, originality_signature=None,
                originality_verified=None, future_write_ready=None, readiness_detail=None,
            )
        )
        text = format_report(report, "en")
        self.assertIn("Timeout reason: idle without output", text)

    def test_cancelled_diagnostic_returns_a_report(self) -> None:
        class CancelledRunner:
            def __init__(self, *_args, **_kwargs):
                self.session_count = 1
            def open(self):
                raise OperationCancelledError("cancelled")
            def close(self):
                pass

        layout = SimpleNamespace(root=Path("C:/pm3"))
        with patch("bambu_rfid_diag.diagnostics.resolve_bundle", return_value=layout), patch(
            "bambu_rfid_diag.diagnostics.ProxmarkRunner", CancelledRunner
        ):
            report = DiagnosticService(locale="en").run("C:/pm3")
        self.assertEqual(report.overall_state, OverallState.ERROR)
        self.assertIn("cancelled", report.summary.lower())
        self.assertEqual(report.pm3_sessions, 1)


if __name__ == "__main__":
    unittest.main()
