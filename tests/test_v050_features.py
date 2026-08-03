from __future__ import annotations

import tempfile
from dataclasses import replace
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.material_library import STATUS_READY, flatten_sources, scan_material_library, uid_index
from bambu_rfid_diag.models import CheckState, CommandResult, TagInfo
from bambu_rfid_diag.ndef import NtagField, build_ntag_ndef, clear_ndef_tlv_area, parse_type2_tlvs
from bambu_rfid_diag.options import (
    NtagEraseOptions,
    NtagWriteOptions,
    ERASE_SCOPE_USER,
    PROFILE_FAST,
    PROFILE_THOROUGH,
    mfc_profile,
    ntag_erase_profile,
    ntag_write_profile,
)
from bambu_rfid_diag.parsers import enrich_mfu_info, parse_default_key_details
from bambu_rfid_diag.sources import load_mfc_source
from bambu_rfid_diag.type2 import NTAG213, NTAG215, NTAG216
from bambu_rfid_diag.writer import WriterService, _clear_firmware_cache_for_tests
from bambu_rfid_diag.workflows.common import bundle_fingerprint
from tests.test_sources import make_source_bytes


def result(command: str, output: str = "[+] ok") -> CommandResult:
    return CommandResult(command, 0, output, 0.01)


def key_table(default: bool) -> str:
    key = "FFFFFFFFFFFF" if default else "------------"
    value = 1 if default else 0
    return "\n".join(
        f"[+]  {sector:03d} | {sector * 4 + 3:03d} | {key} | {value} | {key} | {value}"
        for sector in range(16)
    )


def ntag_info(profile, *, signature_ok: bool) -> str:
    uid = "04 B8 FD AA 7E 26 81"
    signature = "11" * 32 if signature_ok else "00" * 32
    verdict = "successful" if signature_ok else "failed"
    return f"""
Client.... Iceman/master/v4.1-gabcdef123
Bootrom... Iceman/master/v4.1-gabcdef123
OS........ Iceman/master/v4.1-gabcdef123
[+] UID: {uid}
[+] ATQA: 00 44
[+] SAK: 00 [2]
[+] TYPE: {profile.display_name.replace('NXP ', '')} {profile.ndef_capacity + 8}bytes
[+] Lock: 00 00 - 0000000000000000
[=] cfg0 [{profile.config_page}/0x{profile.config_page:02X}]: 04 00 00 FF
[+] {profile.dynamic_lock_page}/0x{profile.dynamic_lock_page:02X} | 00 00 00 BD | ....
[=] TAG IC Signature: {signature}
[+] Signature verification: {verdict}
"""


def make_mfu_dump(profile, uid: bytes = bytes.fromhex("04B8FDAA7E2681")) -> bytes:
    header = bytearray(56)
    header[11] = profile.max_page
    pages = bytearray((profile.max_page + 1) * 4)
    pages[0:3] = uid[:3]
    pages[4:8] = uid[3:]
    pages[10:12] = b"\x00\x00"
    pages[12:16] = bytes((0xE1, 0x10, profile.ndef_capacity // 8, 0x00))
    pages[profile.dynamic_lock_page * 4 : profile.dynamic_lock_page * 4 + 4] = bytes.fromhex("000000BD")
    pages[profile.config_page * 4 : profile.config_page * 4 + 4] = bytes.fromhex("040000FF")
    return bytes(header + pages)


class Type2Runner:
    profile = NTAG215
    signature_ok = False
    instances: list["Type2Runner"] = []

    def __init__(self, layout, _port, **kwargs):
        self.layout = layout
        self.on_event = kwargs.get("on_event")
        self.session_count = 0
        self.commands: list[str] = []
        self.max_pages: list[int] = []
        data = make_mfu_dump(self.profile)
        self.header = bytearray(data[:56])
        self.pages = bytearray(data[56:])
        self.__class__.instances.append(self)

    def __enter__(self):
        self.session_count = 1
        if self.on_event:
            self.on_event("session_started", {"sessions": 1})
        return self

    def __exit__(self, *_args):
        return None

    def run(self, command: str):
        self.commands.append(command)
        return result(command, ntag_info(self.profile, signature_ok=self.signature_ok))

    def read_mfu_page(self, page: int):
        command = f"hf mfu rdbl -b {page}"
        self.commands.append(command)
        data = self.pages[page * 4 : page * 4 + 4]
        return result(command, f"[+] {page}/0x{page:02X} | {data.hex(' ').upper()} | ....")

    def dump_mfu(self, output_name: str):
        command = f"hf mfu dump -f {output_name}"
        self.commands.append(command)
        (self.layout.client_dir / output_name).write_bytes(bytes(self.header + self.pages))
        return result(command, "[+] Saved dump")

    def write_mfu_pages_raw(self, pages, *, max_page=127):
        self.max_pages.append(max_page)
        command = "; ".join(f"RAW {page} {data.hex()}" for page, data in pages)
        self.commands.append(command)
        for page, data in pages:
            self.pages[page * 4 : page * 4 + 4] = data
        return result(command, "\n".join("[+] 0A" for _ in pages))

    def write_mfu_pages(self, pages, *, max_page=127):
        self.max_pages.append(max_page)
        command = "; ".join(f"WRBL {page} {data.hex()}" for page, data in pages)
        self.commands.append(command)
        for page, data in pages:
            self.pages[page * 4 : page * 4 + 4] = data
        return result(command, "\n".join("Write ( ok )" for _ in pages))

    def restore_mfu(self, dump_name: str):
        command = f"hf mfu restore -f {dump_name}"
        self.commands.append(command)
        return result(command, "Restoring data blocks.\nDone!")


class TlvType2Runner(Type2Runner):
    instances: list["TlvType2Runner"] = []
    initial_area = bytes.fromhex(
        "0103A01044"      # Lock Control TLV
        "0304DEADBEEF"    # NDEF TLV
        "FD03112233"      # proprietary TLV
        "FE"              # terminator
    )

    def __init__(self, layout, port, **kwargs):
        super().__init__(layout, port, **kwargs)
        start = self.profile.ndef_first_page * 4
        self.pages[start:start + len(self.initial_area)] = self.initial_area



class LongNdefType2Runner(Type2Runner):
    instances: list["LongNdefType2Runner"] = []

    def __init__(self, layout, port, **kwargs):
        super().__init__(layout, port, **kwargs)
        payload = bytes(range(80))
        area = bytes((0x03, len(payload))) + payload + b"\xFE"
        start = self.profile.ndef_first_page * 4
        self.pages[start:start + len(area)] = area



class ProgrammedMfcRunner:
    instances: list["ProgrammedMfcRunner"] = []

    def __init__(self, layout, _port, **_kwargs):
        self.layout = layout
        self.session_count = 0
        self.commands: list[str] = []
        self.written: bytes | None = None
        self.used_ka = False
        self.__class__.instances.append(self)

    def __enter__(self):
        self.session_count = 1
        return self

    def __exit__(self, *_args):
        return None

    def run(self, command: str):
        self.commands.append(command)
        output = f"""
Client.... Iceman/master/v4.1-gabcdef123
Bootrom... Iceman/master/v4.1-gabcdef123
OS........ Iceman/master/v4.1-gabcdef123
[+] UID: A1 B2 C3 D4
[+] ATQA: 00 04
[+] SAK: 08 [2]
[+] MIFARE Classic 1K
[=] --- Magic Tag Information
[=] <n/a>
{key_table(False)}
"""
        return result(command, output)

    def dump_mfc(self, key_name: str, output_name: str):
        command = f"hf mf dump --1k -k {key_name} -f {output_name}"
        self.commands.append(command)
        if self.written is None:
            data, _keys = make_source_bytes()
        else:
            data = self.written
        (self.layout.client_dir / output_name).write_bytes(data)
        return result(command, "[+] Succeeded in dumping all blocks")

    def mfc_info_with_key(self, key: bytes, *, key_b: bool = False):
        command = f"hf mf info {'-b' if key_b else '-a'} -k {key.hex().upper()}"
        self.commands.append(command)
        return result(
            command,
            "[+] UID: A1 B2 C3 D4\n[+] MIFARE Classic 1K\n[=] --- Magic Tag Information\n[=] <n/a>",
        )

    def write_mfc_block(
        self, block: int, data: bytes, key: bytes, *, key_b: bool = False, force: bool = False
    ):
        command = f"hf mf wrbl --blk {block}{' --force' if force else ''} -k {key.hex().upper()} -d {data.hex().upper()}"
        self.commands.append(command)
        return result(command)

    def read_mfc_block(self, block: int, key: bytes, *, key_b: bool = False):
        data, _keys = make_source_bytes()
        command = f"hf mf rdbl --blk {block} -k {key.hex().upper()}"
        self.commands.append(command)
        hex_data = " ".join(f"{byte:02X}" for byte in data[:16])
        return result(command, f"[=] {block} | {hex_data} | ................")

    def restore_mfc(self, dump_name: str, key_name: str, *, use_keyfile_for_auth: bool = False):
        self.used_ka = use_keyfile_for_auth
        command = f"hf mf restore {'--ka ' if use_keyfile_for_auth else ''}-f {dump_name} -k {key_name}"
        self.commands.append(command)
        self.written = (self.layout.client_dir / dump_name).read_bytes()
        output = "\n".join(f"Sector... {block // 4} block... {block % 4} ( ok )" for block in range(64))
        return result(command, output)


class V050FeatureTests(unittest.TestCase):
    def _layout(self, root: Path):
        client = root / "client"
        client.mkdir(exist_ok=True)
        return SimpleNamespace(root=root, client_dir=client)


    def test_bundle_fingerprint_changes_when_pm3_executable_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            for name in ("pm3.bat", "setup.bat", "pm3", "proxmark3.exe"):
                path = root / name
                path.write_bytes(b"first")
                files[name] = path
            layout = SimpleNamespace(
                root=root,
                pm3_bat=files["pm3.bat"],
                setup_bat=files["setup.bat"],
                pm3_script=files["pm3"],
                proxmark_exe=files["proxmark3.exe"],
            )
            before = bundle_fingerprint(layout)
            files["proxmark3.exe"].write_bytes(b"different-build")
            after = bundle_fingerprint(layout)
        self.assertNotEqual(before, after)

    def test_recommended_firmware_match_is_cached_for_same_bundle_and_port(self):
        _clear_firmware_cache_for_tests()
        Type2Runner.profile = NTAG215
        Type2Runner.signature_ok = True
        Type2Runner.instances = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", Type2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                reports = [
                    WriterService().write_ntag(
                        root,
                        "COM8",
                        fields=[NtagField("URL", "https://example.com", kind="uri")],
                        options=ntag_write_profile("recommended"),
                    )
                    for _ in range(2)
                ]
        self.assertTrue(all(report.success for report in reports))
        self.assertIn("hw version", Type2Runner.instances[0].commands[0])
        self.assertNotIn("hw version", Type2Runner.instances[1].commands[0])
        cached = [
            item for item in reports[1].checks
            if "firmware" in item.name.lower() or "klient" in item.name.lower()
        ]
        self.assertTrue(cached)
        self.assertIn("earlier", cached[0].detail.lower())

    def test_failed_ecc_is_warning_and_does_not_block_thorough_write(self):
        Type2Runner.profile = NTAG215
        Type2Runner.signature_ok = False
        Type2Runner.instances = []
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", Type2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService(on_event=lambda event, payload: events.append((event, payload))).write_ntag(
                    root,
                    None,
                    fields=[NtagField("URL", "https://example.com", kind="uri")],
                    options=ntag_write_profile(PROFILE_THOROUGH),
                )
        self.assertTrue(report.success, report.summary)
        ecc = next(item for item in report.checks if "ECC" in item.name or "Original" in item.name)
        self.assertEqual(ecc.state, CheckState.WARNING)
        self.assertFalse(ecc.blocking)
        self.assertIn("check_added", [event for event, _ in events])
        self.assertEqual(events[-1][0], "operation_finished")

    def test_failed_ecc_does_not_block_thorough_erase(self):
        TlvType2Runner.profile = NTAG215
        TlvType2Runner.signature_ok = False
        TlvType2Runner.instances = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = self._layout(root)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=layout), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", TlvType2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().erase_ntag(
                    root, None, options=ntag_erase_profile(PROFILE_THOROUGH)
                )
        self.assertTrue(report.success, report.summary)
        self.assertTrue(any(command.startswith("RAW") for command in TlvType2Runner.instances[-1].commands))
        ecc = next(item for item in report.checks if "ECC" in item.name or "Original" in item.name)
        self.assertEqual(ecc.state, CheckState.WARNING)
        self.assertFalse(ecc.blocking)

    def test_ntag213_and_216_profiles_are_parsed(self):
        for profile in (NTAG213, NTAG216):
            with self.subTest(profile=profile.identifier):
                tag = enrich_mfu_info(TagInfo(present=True, family="type2"), ntag_info(profile, signature_ok=True))
                self.assertEqual(tag.type2_profile, profile.identifier)
                self.assertEqual(tag.ndef_capacity, profile.ndef_capacity)
                self.assertEqual(tag.dynamic_lock_page, profile.dynamic_lock_page)
                self.assertEqual(tag.config_page, profile.config_page)

    def test_ntag216_write_can_cross_page_127_only_with_detected_profile(self):
        Type2Runner.profile = NTAG216
        Type2Runner.signature_ok = True
        Type2Runner.instances = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", Type2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_ntag(
                    root,
                    None,
                    fields=[
                        NtagField("URL", "https://example.com", kind="uri"),
                        NtagField("Text", "X" * 560),
                    ],
                    options=ntag_write_profile(PROFILE_FAST),
                )
        self.assertTrue(report.success, report.summary)
        runner = Type2Runner.instances[-1]
        raw_pages = [
            int(part.split()[1])
            for command in runner.commands
            for part in command.split("; ")
            if part.startswith("RAW ")
        ]
        self.assertGreater(max(raw_pages), 127)
        self.assertTrue(all(value == NTAG216.ndef_last_page for value in runner.max_pages))

    def test_clear_ndef_preserves_other_tlvs_at_exact_offsets(self):
        area = bytes.fromhex(
            "0103A01044"
            "0304DEADBEEF"
            "FD03112233"
            "FE000000"
        )
        cleared, found = clear_ndef_tlv_area(area)
        self.assertTrue(found)
        self.assertEqual(cleared[:5], area[:5])
        self.assertEqual(cleared[5:11], bytes.fromhex("030000000000"))
        self.assertEqual(cleared[11:], area[11:])
        records = parse_type2_tlvs(cleared)
        self.assertEqual([record.tlv_type for record in records], [0x01, 0x03, 0x00, 0x00, 0x00, 0x00, 0xFD, 0xFE])
        proprietary = next(record for record in records if record.tlv_type == 0xFD)
        self.assertEqual(proprietary.offset, 11)
        self.assertEqual(proprietary.value, bytes.fromhex("112233"))

    def test_safe_ndef_erase_preserves_other_tlvs_and_reports_actual_pages(self):
        TlvType2Runner.profile = NTAG215
        TlvType2Runner.signature_ok = False
        TlvType2Runner.instances = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", TlvType2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().erase_ntag(
                    root, None, options=ntag_erase_profile("recommended")
                )
        self.assertTrue(report.success, report.summary)
        runner = TlvType2Runner.instances[-1]
        start = NTAG215.ndef_first_page * 4
        result_area = bytes(runner.pages[start:start + len(TlvType2Runner.initial_area)])
        self.assertEqual(result_area[:5], TlvType2Runner.initial_area[:5])
        self.assertEqual(result_area[5:11], bytes.fromhex("030000000000"))
        self.assertEqual(result_area[11:], TlvType2Runner.initial_area[11:])
        check = next(item for item in report.checks if "NDEF" in item.name)
        self.assertIn("2", check.detail)

    def test_full_user_erase_zeros_known_profile_range(self):
        Type2Runner.profile = NTAG213
        Type2Runner.signature_ok = True
        Type2Runner.instances = []
        options = replace(ntag_erase_profile(PROFILE_FAST), scope=ERASE_SCOPE_USER)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", Type2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().erase_ntag(root, None, options=options)
        self.assertTrue(report.success, report.summary)
        runner = Type2Runner.instances[-1]
        first = NTAG213.user_first_page * 4
        end = (NTAG213.user_last_page + 1) * 4
        self.assertEqual(bytes(runner.pages[first:end]), bytes(end - first))
        self.assertTrue(any(command.startswith("RAW") for command in runner.commands))

    def test_recommended_write_clears_stale_bytes_from_longer_old_ndef(self):
        LongNdefType2Runner.profile = NTAG215
        LongNdefType2Runner.signature_ok = True
        LongNdefType2Runner.instances = []
        fields = [NtagField("URL", "https://example.com", kind="uri")]
        expected = build_ntag_ndef(fields, "cs", capacity=NTAG215.ndef_capacity)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", LongNdefType2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_ntag(
                    root, None, fields=fields, options=ntag_write_profile("recommended")
                )
        self.assertTrue(report.success, report.summary)
        runner = LongNdefType2Runner.instances[-1]
        start = NTAG215.ndef_first_page * 4
        area = bytes(runner.pages[start:start + NTAG215.ndef_capacity])
        self.assertEqual(area, expected + bytes(NTAG215.ndef_capacity - len(expected)))
        self.assertTrue(any(command.startswith("RAW") for command in runner.commands))

    def test_recommended_write_blocks_nonstandard_tlv_before_raw_write(self):
        TlvType2Runner.profile = NTAG215
        TlvType2Runner.signature_ok = True
        TlvType2Runner.instances = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", TlvType2Runner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_ntag(
                    root, None,
                    fields=[NtagField("URL", "https://example.com", kind="uri")],
                    options=ntag_write_profile("recommended"),
                )
        self.assertFalse(report.success)
        self.assertTrue(any(item.blocking for item in report.checks if "TLV" in item.name))
        self.assertFalse(any(command.startswith("RAW") for command in TlvType2Runner.instances[-1].commands))

    def test_programmed_cuid_with_identical_dump_stops_without_write(self):
        ProgrammedMfcRunner.instances = []
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "PETG" / "A1B2C3D4"
            source_dir.mkdir(parents=True)
            (source_dir / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (source_dir / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            source = load_mfc_source(source_dir)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", ProgrammedMfcRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_bambu(
                    root,
                    source,
                    None,
                    acknowledged_cuid_risk=True,
                    options=mfc_profile("recommended"),
                    library_root=root,
                )
        self.assertTrue(report.success, report.summary)
        self.assertTrue(report.no_change)
        self.assertFalse(ProgrammedMfcRunner.instances[-1].used_ka)
        self.assertIsNotNone(report.backup_path)
        self.assertIn("already-programmed", report.target_classification.lower())

    def test_programmed_cuid_with_different_source_is_blocked_as_unsupported(self):
        ProgrammedMfcRunner.instances = []
        old_dump, old_keys = make_source_bytes()
        new_dump = bytearray(old_dump)
        new_uid = bytes.fromhex("11223344")
        new_dump[:4] = new_uid
        new_dump[4] = new_uid[0] ^ new_uid[1] ^ new_uid[2] ^ new_uid[3]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_dir = root / "PETG" / "A1B2C3D4"
            new_dir = root / "TPU" / "11223344"
            old_dir.mkdir(parents=True)
            new_dir.mkdir(parents=True)
            (old_dir / "hf-mf-A1B2C3D4-dump.bin").write_bytes(old_dump)
            (old_dir / "hf-mf-A1B2C3D4-key.bin").write_bytes(old_keys)
            (new_dir / "hf-mf-11223344-dump.bin").write_bytes(bytes(new_dump))
            (new_dir / "hf-mf-11223344-key.bin").write_bytes(old_keys)
            selected = load_mfc_source(new_dir)
            with patch("bambu_rfid_diag.writer.resolve_bundle", return_value=self._layout(root)), patch(
                "bambu_rfid_diag.writer.ProxmarkWriteRunner", ProgrammedMfcRunner
            ), patch("bambu_rfid_diag.writer.app_data_directory", return_value=root / "appdata"):
                report = WriterService().write_bambu(
                    root, selected, None, acknowledged_cuid_risk=True,
                    options=mfc_profile("recommended"), library_root=root,
                )
        self.assertFalse(report.success)
        self.assertIn("supported", report.summary.lower())
        runner = ProgrammedMfcRunner.instances[-1]
        self.assertFalse(runner.used_ka)
        self.assertFalse(any("wrbl" in command or "restore" in command for command in runner.commands))
        self.assertTrue(report.backup_path)

    def test_zero_default_key_table_is_complete_not_unparseable(self):
        details = parse_default_key_details(key_table(False))
        self.assertTrue(details.complete)
        self.assertEqual(details.sectors_seen, 16)
        self.assertEqual(details.successful_keys, 0)
        self.assertFalse(details.all_default)

    def test_material_quick_validation_and_uid_index(self):
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "PETG" / "A1B2C3D4"
            target.mkdir(parents=True)
            (target / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (target / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            nodes = scan_material_library(root)
            item = flatten_sources(nodes)[0]
            self.assertEqual(item.status, STATUS_READY)
            self.assertEqual(item.authoritative_uid, "A1B2C3D4")
            self.assertEqual(uid_index(nodes)["A1B2C3D4"][0].path, target)

    def test_material_duplicate_uid_is_visible_during_quick_scan(self):
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for branch in ("A", "B"):
                target = root / branch / "A1B2C3D4"
                target.mkdir(parents=True)
                (target / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
                (target / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            items = flatten_sources(scan_material_library(root))
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item.status != STATUS_READY for item in items))
        self.assertTrue(all("2" in item.detail for item in items))



if __name__ == "__main__":
    unittest.main()
