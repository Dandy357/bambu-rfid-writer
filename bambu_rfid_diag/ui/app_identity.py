from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk


_WINDOWS_APP_ID = "BambuRFIDWriter.Desktop"


def apply_application_identity(root: tk.Tk) -> None:
    """Apply the application icon and Windows taskbar identity."""

    asset_root = Path(__file__).resolve().parents[1] / "assets"
    icon_path = asset_root / "app_icon_64.png"
    if icon_path.is_file():
        icon = tk.PhotoImage(master=root, file=str(icon_path))
        root.iconphoto(True, icon)
        # Tk images are reference-counted by Python; retain the object for the
        # complete lifetime of the root window.
        root._bambu_rfid_app_icon = icon  # type: ignore[attr-defined]

    if os.name == "nt":
        try:
            shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
            shell32.SetCurrentProcessExplicitAppUserModelID(_WINDOWS_APP_ID)
        except (AttributeError, OSError):
            # The icon still works even when the optional Windows shell API is
            # unavailable, for example under compatibility layers.
            pass
