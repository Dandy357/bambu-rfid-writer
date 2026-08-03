from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bambu_rfid_diag.options import MfcSourceChecks
from bambu_rfid_diag.sources import SourceValidationError, load_mfc_source


def make_source_bytes(uid: bytes = bytes.fromhex("A1B2C3D4")) -> tuple[bytes, bytes]:
    dump = bytearray(1024)
    dump[:4] = uid
    dump[4] = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
    dump[5:16] = bytes.fromhex("0804006263646566676869")

    key_a_values: list[bytes] = []
    key_b_values: list[bytes] = []
    for sector in range(16):
        key_a = bytes([0x10 + sector]) * 6
        key_b = bytes([0x80 + sector]) * 6
        key_a_values.append(key_a)
        key_b_values.append(key_b)
        trailer_offset = (sector * 4 + 3) * 16
        dump[trailer_offset : trailer_offset + 16] = (
            key_a + bytes.fromhex("FF078069") + key_b
        )
    return bytes(dump), b"".join(key_a_values + key_b_values)


class SourceTests(unittest.TestCase):
    def test_valid_mfc_pair(self) -> None:
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (folder / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            source = load_mfc_source(folder)

        self.assertEqual(source.uid_hex, "A1B2C3D4")
        self.assertEqual(len(source.dump_data), 1024)
        self.assertEqual(len(source.key_data), 192)
        self.assertEqual(len(source.sha256), 64)

    def test_rejects_key_mismatch(self) -> None:
        dump, keys = make_source_bytes()
        damaged_keys = bytearray(keys)
        damaged_keys[6] ^= 0x01
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (folder / "hf-mf-A1B2C3D4-key.bin").write_bytes(damaged_keys)
            with self.assertRaisesRegex(SourceValidationError, "sector 1"):
                load_mfc_source(folder)

    def test_rejects_invalid_bcc(self) -> None:
        dump, keys = make_source_bytes()
        damaged_dump = bytearray(dump)
        damaged_dump[4] ^= 0x01
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "hf-mf-A1B2C3D4-dump.bin").write_bytes(damaged_dump)
            (folder / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            with self.assertRaisesRegex(SourceValidationError, "BCC"):
                load_mfc_source(folder)

    def test_rejects_ambiguous_dump(self) -> None:
        dump, keys = make_source_bytes()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (folder / "hf-mf-A1B2C3D4-dump-001.bin").write_bytes(dump)
            (folder / "hf-mf-A1B2C3D4-key.bin").write_bytes(keys)
            with self.assertRaisesRegex(SourceValidationError, "Multiple candidates"):
                load_mfc_source(folder)

    def test_folder_uid_is_only_a_discovery_hint(self) -> None:
        dump, keys = make_source_bytes(bytes.fromhex("A1B2C3D4"))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "768EEACA"
            folder.mkdir()
            (folder / "source-dump.bin").write_bytes(dump)
            (folder / "source-key.bin").write_bytes(keys)
            source = load_mfc_source(folder)

        self.assertEqual(source.uid_hex, "A1B2C3D4")

    def test_all_source_checks_can_be_disabled(self) -> None:
        dump, keys = make_source_bytes()
        broken = bytearray(dump)
        broken[4] ^= 0xFF
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dump.bin").write_bytes(bytes(broken))
            (root / "key.bin").write_bytes(keys[:-1])
            source = load_mfc_source(
                root, checks=MfcSourceChecks(False, False, False, False, False, False)
            )
        self.assertEqual(source.dump_data, bytes(broken))
        self.assertEqual(len(source.key_data), 191)


if __name__ == "__main__":
    unittest.main()

