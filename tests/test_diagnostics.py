from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.diagnostics import DiagnosticService, _connection_failure_message
from bambu_rfid_diag.models import CommandResult, OverallState
from bambu_rfid_diag.reporting import format_report, save_report


HARDWARE = """
[+] Using UART port COM8
[+] Communicating with PM3 over USB-CDC
MCU....... AT91SAM7S512 Rev B
Memory.... 512 KB ( 74% used )
Target.... PM3 GENERIC
Client.... Iceman/master/v4.21611-604-g53b4e2095
Bootrom... Iceman/master/v4.21611-604-g53b4e2095-suspect
OS........ Iceman/master/v4.21611-604-g53b4e2095-suspect
"""


def result(command: str, output: str) -> CommandResult:
    return CommandResult(command, 0, output, 0.25)


def all_keys() -> str:
    return "\n".join(
        f"[+] | {sector:03d} | FFFFFFFFFFFF | 1 | FFFFFFFFFFFF | 1 |"
        for sector in range(16)
    )


class FakeRunner:
    expected: list[tuple[str, CommandResult]] = []

    def __init__(self, _layout, _port, timeout=60, **_kwargs):
        self.timeout = timeout
        self.session_count = 1

    def open(self):
        return None

    def close(self):
        return None

    def run(self, command: str) -> CommandResult:
        if not self.expected:
            raise AssertionError(f"Unexpected command: {command}")
        expected_command, response = self.expected.pop(0)
        if command != expected_command:
            raise AssertionError(f"Expected {expected_command!r}, received {command!r}")
        return response

    def read_mfu_page(self, page: int) -> CommandResult:
        return self.run(f"hf mfu rdbl -b {page}")


class DiagnosticFlowTests(unittest.TestCase):
    def run_service(
        self,
        responses: list[tuple[str, CommandResult]],
        *,
        expected_family: str | None = None,
    ):
        FakeRunner.expected = list(responses)
        layout = SimpleNamespace(root=Path("C:/Proxmark3"))
        with patch("bambu_rfid_diag.diagnostics.resolve_bundle", return_value=layout), patch(
            "bambu_rfid_diag.diagnostics.ProxmarkRunner", FakeRunner
        ):
            report = DiagnosticService().run(
                "C:/Proxmark3", expected_family=expected_family
            )
        self.assertEqual(FakeRunner.expected, [])
        return report

    def test_mifare_ready_still_returns_ams_caution(self) -> None:
        first_command = "hw version; hf 14a info"
        first_output = HARDWARE + """
[+] UID: DE AD BE EF
[+] ATQA: 00 04
[+] SAK: 08 [2]
[+] Possible type: MIFARE Classic 1K
"""
        second_command = "hf mf info; hf mf chk --1k -k FFFFFFFFFFFF --no-default"
        second_output = """
[=] --- Magic Tag Information
[+] Magic capabilities... Gen 2 / CUID
[=] --- PRNG Information
[+] Prng................. weak
""" + all_keys()
        report = self.run_service(
            [
                (first_command, result(first_command, first_output)),
                (second_command, result(second_command, second_output)),
            ]
        )
        self.assertEqual(report.overall_state, OverallState.CAUTION)
        self.assertTrue(report.tag.future_write_ready)
        self.assertEqual(report.tag.default_key_sectors_seen, 16)

    def test_ntag215_ready_flow(self) -> None:
        first_command = "hw version; hf 14a info"
        first_output = HARDWARE + """
[+] UID: 04 C1 3A AB 7E 26 81
[+] ATQA: 00 44
[+] SAK: 00 [2]
[+] Possible type: NTAG / Ultralight
"""
        second_command = "hf mfu info"
        second_output = """
[+] TYPE: NTAG 215 504bytes (NT2H1511G0DUx)
[+] UID: 04 C1 3A AB 7E 26 81
[+] Lock: 00 00 - 0000000000000000
[=] TAG IC Signature: 0000000000000000000000000000000000000000000000000000000000000000
[+] Signature verification: failed
"""
        lock_command = "hf mfu rdbl -b 130"
        cfg_command = "hf mfu rdbl -b 131"
        report = self.run_service(
            [
                (first_command, result(first_command, first_output)),
                (second_command, result(second_command, second_output)),
                (lock_command, result(lock_command, "[+] 130/0x82 | 00 00 00 BD | ....")),
                (cfg_command, result(cfg_command, "[+] 131/0x83 | 04 00 00 FF | ....")),
            ]
        )
        self.assertEqual(report.overall_state, OverallState.READY)
        self.assertEqual(report.tag.family, "ntag215")
        self.assertTrue(report.tag.future_write_ready)
        signature_check = next(
            check for check in report.checks if check.name == "ECC signature"
        )
        self.assertEqual(signature_check.state.value, "warning")
        self.assertIn("compatible clone", signature_check.detail)

    def test_type2_diagnostic_uses_profile_specific_pages(self) -> None:
        for model, capacity, lock_page, cfg_page, family in (
            ("213", 144, 40, 41, "ntag213"),
            ("216", 888, 226, 227, "ntag216"),
        ):
            with self.subTest(model=model):
                first_command = "hw version; hf 14a info"
                first_output = HARDWARE + """
[+] UID: 04 C1 3A AB 7E 26 81
[+] ATQA: 00 44
[+] SAK: 00 [2]
[+] Possible type: NTAG / Ultralight
"""
                info_command = "hf mfu info"
                info_output = f"""
[+] TYPE: NTAG {model} {capacity}bytes
[+] UID: 04 C1 3A AB 7E 26 81
[+] Lock: 00 00 - 0000000000000000
[+] Signature verification: successful
"""
                lock_command = f"hf mfu rdbl -b {lock_page}"
                cfg_command = f"hf mfu rdbl -b {cfg_page}"
                report = self.run_service([
                    (first_command, result(first_command, first_output)),
                    (info_command, result(info_command, info_output)),
                    (lock_command, result(lock_command, f"[+] {lock_page}/0x{lock_page:02X} | 00 00 00 BD | ....")),
                    (cfg_command, result(cfg_command, f"[+] {cfg_page}/0x{cfg_page:02X} | 04 00 00 FF | ....")),
                ])
                self.assertEqual(report.overall_state, OverallState.READY)
                self.assertEqual(report.tag.family, family)
                self.assertTrue(report.tag.future_write_ready)

    def test_cuid_check_rejects_type2_without_running_type2_diagnostic(self) -> None:
        command = "hw version; hf 14a info"
        output = HARDWARE + """
[+] UID: 04 C1 3A AB 7E 26 81
[+] ATQA: 00 44
[+] SAK: 00 [2]
[+] Possible type: NTAG / Ultralight
"""
        report = self.run_service(
            [(command, result(command, output))], expected_family="mfc1k"
        )
        self.assertEqual(report.overall_state, OverallState.BLOCKED)
        self.assertIn("CUID", report.summary)

    def test_ndef_check_rejects_mifare_without_running_key_checks(self) -> None:
        command = "hw version; hf 14a info"
        output = HARDWARE + """
[+] UID: DE AD BE EF
[+] ATQA: 00 04
[+] SAK: 08 [2]
[+] Possible type: MIFARE Classic 1K
"""
        report = self.run_service(
            [(command, result(command, output))], expected_family="type2"
        )
        self.assertEqual(report.overall_state, OverallState.BLOCKED)
        self.assertIn("NDEF", report.summary)

    def test_no_tag_stops_after_initial_read(self) -> None:
        command = "hw version; hf 14a info"
        report = self.run_service(
            [(command, result(command, HARDWARE + "\n[-] No tag found"))]
        )
        self.assertEqual(report.overall_state, OverallState.NO_TAG)
        self.assertFalse(report.tag.present)

    def test_locked_or_inaccessible_com_port_has_actionable_message(self) -> None:
        output = """
[+] Using UART port COM8
[!] ERROR: invalid serial port COM8
"""
        detail, summary = _connection_failure_message(output, "COM8")
        self.assertIn("could not open COM8", detail)
        self.assertIn("pm3.bat", detail)
        self.assertIn("proxmark3.exe", detail)
        self.assertIn("probably", summary)

        command = "hw version; hf 14a info"
        failed = CommandResult(command, 1, output, 0.21)
        report = self.run_service([(command, failed)])
        self.assertEqual(report.overall_state, OverallState.ERROR)
        self.assertIn("COM8 could not be opened", report.summary)
        communication_check = next(
            check for check in report.checks if check.name == "Proxmark3 communication"
        )
        self.assertIn("Other Proxmark3 clients must be closed", communication_check.detail)

    def test_report_is_written_as_utf8_text(self) -> None:
        command = "hw version; hf 14a info"
        report = self.run_service(
            [(command, result(command, HARDWARE + "\n[-] No tag found"))]
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LOCALAPPDATA": directory}
        ):
            path = save_report(report)
            self.assertTrue(path.is_file())
            content = path.read_text(encoding="utf-8-sig")
            self.assertEqual(content, format_report(report))
            self.assertIn("This diagnostic run does not write to the tag", content)


if __name__ == "__main__":
    unittest.main()
