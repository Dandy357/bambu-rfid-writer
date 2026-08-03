from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bambu_rfid_diag.domain.commands import CommandResult
from bambu_rfid_diag.pm3.results import (
    mfc_dump_succeeded,
    mfc_restore_succeeded,
    mfu_dump_succeeded,
    mfu_restore_succeeded,
    mfu_wrbl_batch_succeeded,
    raw_page_batch_succeeded,
)


def command(output: str, returncode: int = 0) -> CommandResult:
    return CommandResult("test", returncode, output, 0.1)


class TypedPm3ResultTests(unittest.TestCase):
    def test_raw_page_write_requires_one_ack_per_page(self) -> None:
        self.assertTrue(raw_page_batch_succeeded(command("[+] 0A\n[+] 0A"), 2))
        self.assertFalse(raw_page_batch_succeeded(command("[+] 0A"), 2))
        self.assertFalse(raw_page_batch_succeeded(command(""), 1))
        self.assertFalse(raw_page_batch_succeeded(command("hf 14a raw ..."), 1))

    def test_wrbl_requires_one_explicit_success_per_page(self) -> None:
        self.assertTrue(
            mfu_wrbl_batch_succeeded(command("Write ( ok )\nWrite ( ok )"), 2)
        )
        self.assertFalse(mfu_wrbl_batch_succeeded(command("Write ( fail )"), 1))
        self.assertFalse(mfu_wrbl_batch_succeeded(command("[+] ok"), 1))

    def test_mfc_restore_requires_all_64_blocks(self) -> None:
        complete = "\n".join(
            f"Sector... {block // 4} block... {block % 4} ( ok )"
            for block in range(64)
        )
        self.assertTrue(mfc_restore_succeeded(command(complete)))
        self.assertFalse(mfc_restore_succeeded(command(complete.rsplit("\n", 1)[0])))
        self.assertFalse(mfc_restore_succeeded(command("[+] Done")))

    def test_mfu_restore_requires_start_and_completion(self) -> None:
        self.assertTrue(
            mfu_restore_succeeded(command("Restoring data blocks.\nDone!"))
        )
        self.assertFalse(mfu_restore_succeeded(command("Restoring data blocks.")))
        self.assertFalse(mfu_restore_succeeded(command("Done!")))

    def test_transport_failure_overrides_success_text(self) -> None:
        failed_raw = command("[+] 0A", returncode=1)
        failed_restore = command(
            "Restoring data blocks.\nDone!",
            returncode=1,
        )
        self.assertFalse(raw_page_batch_succeeded(failed_raw, 1))
        self.assertFalse(mfu_restore_succeeded(failed_restore))

    def test_dump_validators_require_real_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mfc = root / "mfc.bin"
            mfu = root / "mfu.bin"
            mfc.write_bytes(bytes(1024))
            mfu.write_bytes(bytes(56 + 16))
            self.assertTrue(
                mfc_dump_succeeded(
                    command("Succeeded in dumping all blocks"), mfc
                )
            )
            self.assertFalse(mfc_dump_succeeded(command("[+] Saved"), mfc))
            self.assertTrue(mfu_dump_succeeded(command("[+] Saved"), mfu))
            self.assertFalse(mfu_dump_succeeded(command("[+] completed"), mfu))
            mfu.write_bytes(bytes(71))
            self.assertFalse(mfu_dump_succeeded(command("[+] Saved"), mfu))


if __name__ == "__main__":
    unittest.main()
