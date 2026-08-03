from __future__ import annotations

import os
import shutil
from pathlib import Path


def app_data_directory() -> Path:
    """Return the per-user application data directory."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "BambuRFIDWriter"
    return Path.home() / ".bambu_rfid_writer"


def diagnostic_log_directory() -> Path:
    """Return the directory containing read-only diagnostic reports."""
    return app_data_directory() / "logs"


def clear_user_data_directory() -> Path:
    """Remove the complete per-user data directory if it exists."""

    directory = app_data_directory()
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        pass
    return directory
