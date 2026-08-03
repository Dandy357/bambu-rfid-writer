from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence


def require(path: Path, description: str) -> None:
    """Stop the build with a clear message when a required input is missing."""
    if not path.exists():
        raise SystemExit(f"Missing {description}: {path}")


def build_command(root: Path, python_executable: str | None = None) -> list[str]:
    """Return the complete PyInstaller command used by the Windows helper."""
    executable = python_executable or sys.executable
    return [
        executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(root / "dist"),
        "--workpath",
        str(root / "build"),
        str(root / "Bambu_RFID_Writer.spec"),
    ]


def run_build(root: Path, command: Sequence[str]) -> int:
    """Run PyInstaller and verify that the expected executable was produced."""
    completed = subprocess.run(list(command), cwd=root, check=False)
    if completed.returncode != 0:
        return completed.returncode

    output = root / "dist" / "Bambu_RFID_Writer.exe"
    if not output.is_file() or output.stat().st_size == 0:
        print(f"Build completed without the expected EXE: {output}", file=sys.stderr)
        return 2

    print(f"EXE created: {output}")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    require(root / "Bambu_RFID_Writer.spec", "PyInstaller spec file")
    require(root / "Bambu_RFID_Writer.pyw", "application entry point")
    require(root / "bambu_rfid_diag" / "assets" / "app_icon.ico", "application icon")
    require(root / "bambu_rfid_diag" / "assets", "asset directory")
    require(root / "bambu_rfid_diag" / "locales", "localization directory")
    return run_build(root, build_command(root))


if __name__ == "__main__":
    raise SystemExit(main())
