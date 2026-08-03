from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.models import CommandResult
from bambu_rfid_diag.ndef import NtagField
from bambu_rfid_diag.options import (
    MfcWriteOptions,
    NtagEraseOptions,
    NtagWriteOptions,
    NTAG_METHOD_RAW,
    ERASE_SCOPE_USER,
    NTAG_METHOD_RESTORE,
    PROFILE_FAST,
    mfc_profile,
    ntag_erase_profile,
    ntag_write_profile,
)
from bambu_rfid_diag.sources import load_mfc_source
from bambu_rfid_diag.writer import PM3_PIPE_PAGE_BATCH, WriterService
from tests.test_sources import make_source_bytes


def result(command: str, output: str = "[+] ok") -> CommandResult:
    return CommandResult(command, 0, output, 0.1)


def mfc_preflight() -> str:
    keys = "\n".join(
        f"[+] | {sector:03d} | FFFFFFFFFFFF | 1 | FFFFFFFFFFFF | 1 |"
        for sector in range(16)
    )
    return f"""
[+] Using UART port COM8
[+] Communicating with PM3 over USB-CDC
Client.... Iceman/master/v4.1-gabcdef123
Bootrom... Iceman/master/v4.1-gabcdef123
OS........ Iceman/master/v4.1-gabcdef123
[+] UID: AA 7C 25 A6
[+] ATQA: 00 04
[+] SAK: 08 [2]
[+] MIFARE Classic 1K
[+] Magic capabilities... Gen 2 / CUID
{keys}
"""


def ntag_preflight(uid: str = "04 B8 FD AA 7E 26 81") -> str:
    return f"""
[+] Using UART port COM8
[+] Communicating with PM3 over USB-CDC
Client.... Iceman/master/v4.1-gabcdef123
Bootrom... Iceman/master/v4.1-gabcdef123
OS........ Iceman/master/v4.1-gabcdef123
[+] UID: {uid}
[+] ATQA: 00 44
[+] SAK: 00 [2]
[+] TYPE: NTAG 215 504bytes
[+] Static lock bytes   : 00 00
[+] Dynamic lock bytes  : 00 00 00
[+] AUTH0               : FF
[+] Signature verification: successful
"""


def make_mfu_dump(uid: bytes) -> bytes:
    header = bytearray(56)
    header[11] = 134
    pages = bytearray(135 * 4)
    pages[0:3] = uid[0:3]
    pages[4:8] = uid[3:7]
    pages[10:12] = b"\x00\x00"
    pages[12:16] = bytes.fromhex("E1103E00")
    pages[130 * 4 : 131 * 4] = bytes.fromhex("000000BD")
    pages[131 * 4 : 132 * 4] = bytes.fromhex("040000FF")
    return bytes(header + pages)


class FakeUnifiedRunner:
    mode = "mfc"
    initial_mfu = make_mfu_dump(bytes.fromhex("04B8FDAA7E2681"))
    instances: list["FakeUnifiedRunner"] = []

    def __init__(self, layout, _port, **_kwargs):
        self.layout = layout
        self.session_count = 0
        self.commands: list[str] = []
        self.mfc_written: bytes | None = None
        self.mfu_header = bytearray(self.initial_mfu[:56])
        self.mfu_pages = bytearray(self.initial_mfu[56:])
        self.__class__.instances.append(self)

    def __enter__(self):
        self.session_count = 1
        return self

    def __exit__(self, *_args):
        return None

    def run(self, command: str) -> CommandResult:
        self.commands.append(command)
        if "hf mfu" in command or self.mode == "ntag":
            return result(command, ntag_preflight())
        if self.mfc_written is not None and command == "hf 14a info; hf mf info":
            uid = " ".join(f"{byte:02X}" for byte in self.mfc_written[:4])
            return result(command, f"[+] UID: {uid}\n[+] ATQA: 00 04\n[+] SAK: 08 [2]\n[+] MIFARE Classic 1K")
        return result(command, mfc_preflight())

    def dump_mfc(self, key_name: str, output_name: str) -> CommandResult:
        command = f"hf mf dump --1k -k {key_name} -f {output_name}"
        self.commands.append(command)
        path = self.layout.client_dir / output_name
        if "default_key" in key_name:
            data = bytearray(1024)
            uid = bytes.fromhex("AA7C25A6")
            data[:4] = uid
            data[4] = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
            path.write_bytes(data)
        else:
            path.write_bytes(self.mfc_written or b"")
        return result(command, "[+] Succeeded in dumping all blocks")

    def restore_mfc(self, dump_name: str, key_name: str, *, use_keyfile_for_auth: bool = False) -> CommandResult:
        auth = " --ka" if use_keyfile_for_auth else ""
        command = f"hf mf restore --1k --force{auth} -f {dump_name} -k {key_name}"
        self.commands.append(command)
        self.mfc_written = (self.layout.client_dir / dump_name).read_bytes()
        output = "\n".join(f"Sector... {block // 4} block... {block % 4} ( ok )" for block in range(64))
        return result(command, output)

    def dump_mfu(self, output_name: str) -> CommandResult:
        command = f"hf mfu dump -f {output_name}"
        self.commands.append(command)
        (self.layout.client_dir / output_name).write_bytes(bytes(self.mfu_header + self.mfu_pages))
        return result(command, "[+] Saved dump")

    def write_mfu_pages_raw(self, pages: list[tuple[int, bytes]], *, max_page: int = 127) -> CommandResult:
        command = "; ".join(f"RAW {page} {data.hex()}" for page, data in pages)
        self.commands.append(command)
        for page, data in pages:
            self.mfu_pages[page * 4 : page * 4 + 4] = data
        return result(command, "\n".join("[+] 0A" for _ in pages))

    def write_mfu_pages(self, pages: list[tuple[int, bytes]], *, max_page: int = 127) -> CommandResult:
        command = "; ".join(f"WRBL {page} {data.hex()}" for page, data in pages)
        self.commands.append(command)
        for page, data in pages:
            self.mfu_pages[page * 4 : page * 4 + 4] = data
        return result(command, "\n".join("Write ( ok )" for _ in pages))

    def restore_mfu(self, dump_name: str) -> CommandResult:
        command = f"hf mfu restore -f {dump_name}"
        self.commands.append(command)
        data = (self.layout.client_dir / dump_name).read_bytes()
        self.mfu_header = bytearray(data[:56])
        image_pages = data[56:]
        # Standard restore keeps manufacturer/config pages and writes user memory.
        self.mfu_pages[4 * 4 : 130 * 4] = image_pages[4 * 4 : 130 * 4]
        return result(command, "Restoring data blocks.\nDone!")


class WriterFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeUnifiedRunner.instances = []
        FakeUnifiedRunner.mode = "mfc"

    def _layout(self, root: Path):
        client = root / "client"
        client.mkdir(exist_ok=True)
        return SimpleNamespace(root=root, client_dir=client)

    def test_mfc_recommended_uses_one_session_and_exact_readback(self) -> None:
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (source / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            layout = self._layout(root)
            FakeUnifiedRunner.mode = "mfc"
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_bambu(
                    root, source, None, acknowledged_cuid_risk=True
                )
        self.assertTrue(report.success, report.summary)
        self.assertTrue(report.verified)
        self.assertEqual(report.pm3_sessions, 1)
        self.assertEqual(len(FakeUnifiedRunner.instances), 1)
        self.assertTrue(any("restore" in command for command in FakeUnifiedRunner.instances[0].commands))

    def test_mfc_fast_profile_keeps_preflight_but_skips_backup_and_readback(self) -> None:
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "dump.bin").write_bytes(dump)
            (source / "key.bin").write_bytes(keys)
            layout = self._layout(root)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_bambu(
                    root, source, None, acknowledged_cuid_risk=True,
                    options=mfc_profile(PROFILE_FAST),
                )
        self.assertTrue(report.success, report.summary)
        self.assertFalse(report.verified)
        commands = FakeUnifiedRunner.instances[0].commands
        self.assertEqual(len(commands), 2)
        self.assertIn("hf 14a info", commands[0])
        self.assertIn("hf mf chk", commands[0])
        self.assertIn("restore", commands[1])
        self.assertIsNone(report.backup_path)

    def test_ntag_raw_two_phase_is_one_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            FakeUnifiedRunner.mode = "ntag"
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_ntag(
                    root, None,
                    fields=[NtagField("Odkaz", "https://example.com", False, "uri"), NtagField("Typ", "PLA")],
                    options=NtagWriteOptions(method=NTAG_METHOD_RAW),
                )
        self.assertTrue(report.success, report.summary)
        self.assertEqual(report.pm3_sessions, 1)
        commands = FakeUnifiedRunner.instances[0].commands
        raw = [command for command in commands if command.startswith("RAW")]
        self.assertGreaterEqual(len(raw), 3)  # invalidate, one or more body batches, commit
        for command in raw:
            self.assertLessEqual(command.count("RAW "), PM3_PIPE_PAGE_BATCH)
        self.assertTrue(any(command.startswith("hf mfu dump") for command in commands))

    def test_ntag_restore_without_saved_backup_uses_temporary_dump(self) -> None:
        options = ntag_write_profile(PROFILE_FAST)
        options = NtagWriteOptions(
            profile=PROFILE_FAST,
            method=NTAG_METHOD_RESTORE,
            two_phase=False,
            backup=False,
            final_verify=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            FakeUnifiedRunner.mode = "ntag"
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_ntag(
                    root, None,
                    fields=[NtagField("URL", "https://example.com", False, "uri")],
                    options=options,
                )
        self.assertTrue(report.success, report.summary)
        self.assertIsNone(report.backup_path)
        commands = FakeUnifiedRunner.instances[0].commands
        self.assertEqual(sum(command.startswith("hf mfu dump") for command in commands), 1)
        self.assertEqual(sum("restore -f" in command for command in commands), 1)

    def test_ntag_fast_profile_keeps_minimum_preflight_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            FakeUnifiedRunner.mode = "ntag"
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_ntag(
                    root, None,
                    fields=[NtagField("URL", "https://example.com", False, "uri")],
                    options=ntag_write_profile(PROFILE_FAST),
                )
        self.assertTrue(report.success, report.summary)
        commands = FakeUnifiedRunner.instances[0].commands
        self.assertGreaterEqual(len(commands), 1)
        self.assertIn("hf 14a info", commands[0])
        write_commands = commands[1:]
        self.assertTrue(write_commands)
        self.assertTrue(all(command.startswith("RAW") for command in write_commands))
        self.assertTrue(all(command.count("RAW ") <= PM3_PIPE_PAGE_BATCH for command in write_commands))

    def test_ntag_safe_erase_fast_reads_tlv_map_and_skips_empty_tag(self) -> None:
        options = ntag_erase_profile(PROFILE_FAST)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            FakeUnifiedRunner.mode = "ntag"
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().erase_ntag(root, None, options=options)
        self.assertTrue(report.success, report.summary)
        self.assertFalse(report.verified)
        commands = FakeUnifiedRunner.instances[0].commands
        self.assertEqual(len(commands), 2)
        self.assertIn("hf 14a info", commands[0])
        self.assertTrue(commands[1].startswith("hf mfu dump"))
        self.assertFalse(any(command.startswith("RAW") for command in commands))
        self.assertEqual(FakeUnifiedRunner.instances[0].session_count, 1)

    def test_ntag_full_user_erase_reports_progress_for_each_safe_batch(self) -> None:
        options = replace(ntag_erase_profile(PROFILE_FAST), scope=ERASE_SCOPE_USER)
        messages: list[str] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            FakeUnifiedRunner.mode = "ntag"
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().erase_ntag(
                    root, None, options=options, on_progress=messages.append
                )
        self.assertTrue(report.success, report.summary)
        batch_messages = [message for message in messages if "Batch" in message]
        self.assertEqual(len(batch_messages), 18)
        self.assertIn("1/18", batch_messages[0])
        self.assertIn("18/18", batch_messages[-1])

    def test_prevalidated_source_is_not_reloaded(self) -> None:
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_folder = root / "source"
            source_folder.mkdir()
            (source_folder / "dump.bin").write_bytes(dump)
            (source_folder / "key.bin").write_bytes(keys)
            source = load_mfc_source(source_folder)
            layout = self._layout(root)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", FakeUnifiedRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"), patch(
                "bambu_rfid_diag.writer.load_mfc_source", side_effect=AssertionError("source reloaded")
            ):
                report = WriterService().write_bambu(
                    root, source, None, acknowledged_cuid_risk=True,
                    options=mfc_profile(PROFILE_FAST),
                )
        self.assertTrue(report.success, report.summary)


if __name__ == "__main__":
    unittest.main()
