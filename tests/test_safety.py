from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bambu_rfid_diag.proxmark import (
    BundleValidationError,
    UnsafeCommandError,
    PM3_PIPE_SAFE_COMMAND_LENGTH,
    ProxmarkWriteRunner,
    make_runner_batch,
    resolve_bundle,
    validate_port,
    validate_read_only_command,
)
from bambu_rfid_diag.models import CommandResult
from bambu_rfid_diag.options import NTAG_METHOD_RAW, NTAG_METHOD_WRBL
from bambu_rfid_diag.writer import PM3_PIPE_PAGE_BATCH, WriterService


class SafetyTests(unittest.TestCase):
    def test_write_commands_are_rejected(self) -> None:
        forbidden = (
            "hf mf restore --1k -f dump.bin -k key.bin --force",
            "hf mfu restore -f dump.bin",
            "hf mf wrbl --blk 0 -d 00000000000000000000000000000000",
            "hf mfu wrbl -b 4 -d 00000000",
            "hf mfu wipe",
        )
        for command in forbidden:
            with self.subTest(command=command), self.assertRaises(UnsafeCommandError):
                validate_read_only_command(command)

        with self.assertRaises(UnsafeCommandError):
            validate_read_only_command("hw version; hf mfu restore -f dump.bin")

    def test_proxmark_safety_errors_are_localized(self) -> None:
        with self.assertRaisesRegex(
            UnsafeCommandError,
            "not in the list of permitted diagnostic operations",
        ):
            validate_read_only_command("hf mfu wipe", locale="en")

        runner = ProxmarkWriteRunner(object(), None, locale="en")  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            UnsafeCommandError,
            "limited to user pages 4–127",
        ):
            runner.write_mfu_page(128, b"\x00" * 4)

    def test_invalid_ports_are_rejected(self) -> None:
        self.assertEqual(validate_port("com8"), "COM8")
        self.assertIsNone(validate_port("Automatic"))
        self.assertIsNone(validate_port("Automatic detection"))
        self.assertIsNone(validate_port("Automatická detekce", "cs"))
        for value in ("COM0", "COM1000", "COM8 & calc", "8", ""):
            if value == "":
                self.assertIsNone(validate_port(value))
            else:
                with self.subTest(port=value), self.assertRaises(ValueError):
                    validate_port(value)

    def test_only_known_read_commands_enter_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "client").mkdir()
            (root / "pm3.bat").write_text(
                "@echo off\ncd client\ncall setup.bat\nbash pm3\n", encoding="utf-8"
            )
            for name in ("setup.bat", "pm3", "proxmark3.exe"):
                (root / "client" / name).write_bytes(b"placeholder")
            layout = resolve_bundle(root)
            batch = make_runner_batch(layout, "hw version; hf 14a info", "COM8")
            self.assertIn("bash pm3 -p COM8 --incognito", batch)
            self.assertIn('"hw version; hf 14a info"', batch)
            self.assertNotIn("restore", batch.lower())
            self.assertNotIn("wrbl", batch.lower())

    def test_bundle_path_with_batch_metacharacters_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pm3%bundle") as directory:
            root = Path(directory)
            (root / "client").mkdir()
            (root / "pm3.bat").write_text(
                "@echo off\ncd client\ncall setup.bat\nbash pm3\n", encoding="utf-8"
            )
            for name in ("setup.bat", "pm3", "proxmark3.exe"):
                (root / "client" / name).write_bytes(b"placeholder")
            layout = resolve_bundle(root)
            with self.assertRaises(BundleValidationError):
                make_runner_batch(layout, "hw version", "COM8")

    def test_write_runner_only_builds_bounded_commands(self) -> None:
        runner = ProxmarkWriteRunner(object(), "COM8")  # type: ignore[arg-type]
        captured: list[str] = []

        def fake_execute(command: str, prefix: str = "") -> CommandResult:
            captured.append(command)
            return CommandResult(command, 0, "ok", 0.1)

        with patch.object(runner, "_execute", side_effect=fake_execute):
            runner.restore_mfc("source_dump.bin", "source_key.bin")
            runner.dump_mfc("source_key.bin", "verify.bin")
            runner.dump_mfu("backup.bin")
            runner.restore_mfu("generated.bin")
            runner.write_mfu_page(4, bytes.fromhex("0300AABB"))
            runner.write_mfu_pages([(5, b"\x00" * 4), (6, bytes.fromhex("11223344"))])
            runner.write_mfu_pages_raw([(4, bytes.fromhex("0300AABB")), (5, bytes.fromhex("11223344"))])

        self.assertEqual(
            captured[0],
            "hf mf restore --1k --force -f source_dump.bin -k source_key.bin",
        )
        self.assertEqual(captured[1], "hf mf dump --1k -k source_key.bin -f verify.bin")
        self.assertEqual(captured[2], "hf mfu dump -f backup.bin")
        self.assertEqual(captured[3], "hf mfu restore -f generated.bin")
        self.assertEqual(captured[4], "hf mfu wrbl -b 4 -d 0300AABB")
        self.assertEqual(
            captured[5],
            "hf mfu wrbl -b 5 -d 00000000; hf mfu wrbl -b 6 -d 11223344",
        )
        self.assertEqual(
            captured[6],
            "hf 14a raw -s -c -k A2040300AABB; hf 14a raw -c A20511223344",
        )

    def test_page_writes_are_split_below_pm3_pipe_limit(self) -> None:
        pages = [(page, b"\x00" * 4) for page in range(4, 128)]
        for method in (NTAG_METHOD_RAW, NTAG_METHOD_WRBL):
            with self.subTest(method=method):
                runner = ProxmarkWriteRunner(object(), None)  # type: ignore[arg-type]
                captured: list[str] = []

                def fake_execute(command: str, prefix: str = "") -> CommandResult:
                    captured.append(command)
                    page_count = command.count("; ") + 1
                    if method == NTAG_METHOD_RAW:
                        output = "\n".join("[+] 0A" for _ in range(page_count))
                    else:
                        output = "\n".join("Write ( ok )" for _ in range(page_count))
                    return CommandResult(command, 0, output, 0.1)

                with patch.object(runner, "_execute", side_effect=fake_execute):
                    results = WriterService()._write_pages(runner, method, pages)
                self.assertEqual(len(results), 18)
                self.assertTrue(all(len(command.encode("ascii")) <= PM3_PIPE_SAFE_COMMAND_LENGTH for command in captured))
                self.assertTrue(all(command.count("; ") + 1 <= PM3_PIPE_PAGE_BATCH for command in captured))

    def test_interactive_pipe_rejects_oversized_command_lines(self) -> None:
        runner = ProxmarkWriteRunner(object(), None, locale="en")  # type: ignore[arg-type]
        oversized = "x" * (PM3_PIPE_SAFE_COMMAND_LENGTH + 1)
        with self.assertRaisesRegex(UnsafeCommandError, "safe interactive-session limit"):
            runner._execute(oversized)

    def test_write_runner_rejects_injection_and_protected_pages(self) -> None:
        runner = ProxmarkWriteRunner(object(), None)  # type: ignore[arg-type]
        with self.assertRaises(UnsafeCommandError):
            runner.restore_mfc("dump.bin & calc", "key.bin")
        with self.assertRaises(UnsafeCommandError):
            runner.dump_mfu("../outside.bin")
        with self.assertRaises(UnsafeCommandError):
            runner.write_mfu_page(3, b"\x00" * 4)
        with self.assertRaises(UnsafeCommandError):
            runner.write_mfu_page(128, b"\x00" * 4)
        with self.assertRaises(UnsafeCommandError):
            runner.write_mfu_page(4, b"\x00" * 3)
        with self.assertRaises(UnsafeCommandError):
            runner.write_mfu_pages([])
        with self.assertRaises(UnsafeCommandError):
            runner.write_mfu_pages([(4, b"\x00" * 4), (4, b"\x01" * 4)])
        with self.assertRaises(UnsafeCommandError):
            runner.write_mfu_pages([(127, b"\x00" * 4), (128, b"\x00" * 4)])


if __name__ == "__main__":
    unittest.main()
