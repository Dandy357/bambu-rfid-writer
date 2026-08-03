from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.models import CommandResult
from bambu_rfid_diag.ndef_reader import NdefReadService
from bambu_rfid_diag.presentation.ndef_read import format_ndef_read_result


HARDWARE_TYPE2 = """
[+] Using UART port COM8
[+] Communicating with PM3 over USB-CDC
MCU....... AT91SAM7S512 Rev B
Memory.... 512 KB ( 74% used )
Target.... PM3 GENERIC
Client.... Iceman/master/v4.21611
Bootrom... Iceman/master/v4.21611
OS........ Iceman/master/v4.21611
[+] UID: 04 11 22 44 55 66 77
[+] ATQA: 00 44
[+] SAK: 00 [2]
[+] Possible type: NTAG / Ultralight
"""

TYPE2_INFO = """
[+] TYPE: NTAG 215 504bytes (NT2H1511G0DUx)
[+] UID: 04 11 22 44 55 66 77
[+] Lock: 00 00 - 0000000000000000
"""


class FakeReadRunner:
    fixture = Path(__file__).parent / "fixtures" / "hf-mfu-sample.bin"

    def __init__(self, layout, _port, **_kwargs):
        self.layout = layout

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def run(self, command: str) -> CommandResult:
        if command == "hw version; hf 14a info":
            return CommandResult(command, 0, HARDWARE_TYPE2, 0.1)
        if command == "hf mfu info":
            return CommandResult(command, 0, TYPE2_INFO, 0.1)
        raise AssertionError(f"Unexpected command: {command}")

    def dump_mfu(self, output_name: str) -> CommandResult:
        target = self.layout.client_dir / output_name
        target.write_bytes(self.fixture.read_bytes())
        return CommandResult(
            f"hf mfu dump -f {output_name}",
            0,
            f"[+] Saved {target.name}",
            0.1,
        )


class NdefReadServiceTests(unittest.TestCase):
    def test_reads_and_formats_text_and_url_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory)
            layout = SimpleNamespace(root=client, client_dir=client)
            with patch(
                "bambu_rfid_diag.ndef_reader.resolve_bundle", return_value=layout
            ), patch(
                "bambu_rfid_diag.ndef_reader.ProxmarkWriteRunner", FakeReadRunner
            ):
                result = NdefReadService().read(client, "Automatic detection")

            self.assertEqual(result.uid, "04 11 22 44 55 66 77")
            self.assertEqual(result.profile_name, "NXP NTAG215")
            self.assertEqual(len(result.records), 2)
            text = format_ndef_read_result(result)
            self.assertIn("https://example.com/filament/sample?id=12345", text)
            self.assertIn("Example Filaments", text)
            self.assertFalse(any(client.glob("brw_*")))

    def test_rejects_mifare_classic_before_dumping(self) -> None:
        mifare_output = HARDWARE_TYPE2.replace(
            "[+] SAK: 00 [2]\n[+] Possible type: NTAG / Ultralight",
            "[+] SAK: 08 [2]\n[+] Possible type: MIFARE Classic 1K",
        ).replace("[+] ATQA: 00 44", "[+] ATQA: 00 04")

        class MifareRunner(FakeReadRunner):
            def run(self, command: str) -> CommandResult:
                if command == "hw version; hf 14a info":
                    return CommandResult(command, 0, mifare_output, 0.1)
                return super().run(command)

            def dump_mfu(self, output_name: str) -> CommandResult:
                raise AssertionError("A MIFARE Classic tag must not be dumped as MFU")

        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory)
            layout = SimpleNamespace(root=client, client_dir=client)
            with patch(
                "bambu_rfid_diag.ndef_reader.resolve_bundle", return_value=layout
            ), patch(
                "bambu_rfid_diag.ndef_reader.ProxmarkWriteRunner", MifareRunner
            ):
                with self.assertRaisesRegex(ValueError, "not an NFC Type 2"):
                    NdefReadService().read(client)


if __name__ == "__main__":
    unittest.main()
