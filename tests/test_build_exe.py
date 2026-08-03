from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.build_exe import build_command, run_build


class ExeBuildHelperTests(unittest.TestCase):
    def test_build_command_always_ends_with_the_spec_script_input(self) -> None:
        root = Path("C:/Bambu RFID Writer")
        command = build_command(root, "C:/build-tools/python.exe")

        self.assertEqual(command[:3], ["C:/build-tools/python.exe", "-m", "PyInstaller"])
        self.assertEqual(command[-1], str(root / "Bambu_RFID_Writer.spec"))
        self.assertIn(str(root / "dist"), command)
        self.assertIn(str(root / "build"), command)

    def test_success_requires_the_expected_nonempty_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "dist" / "Bambu_RFID_Writer.exe"
            output.parent.mkdir()
            output.write_bytes(b"MZ")
            completed = SimpleNamespace(returncode=0)
            with patch(
                "tools.build_exe.subprocess.run",
                return_value=completed,
            ) as run, redirect_stdout(io.StringIO()):
                result = run_build(
                    root,
                    ["python", "-m", "PyInstaller", "app.spec"],
                )

        self.assertEqual(result, 0)
        run.assert_called_once_with(
            ["python", "-m", "PyInstaller", "app.spec"], cwd=root, check=False
        )


if __name__ == "__main__":
    unittest.main()
