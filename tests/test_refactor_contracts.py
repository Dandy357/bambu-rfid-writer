from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.domain.operation_events import UiEvent, UiEventKind
from bambu_rfid_diag.infrastructure.paths import (
    app_data_directory,
    clear_user_data_directory,
)
from bambu_rfid_diag.infrastructure.settings import SettingsRepository
from bambu_rfid_diag.models import APP_VERSION
from bambu_rfid_diag.options import (
    NtagEraseOptions,
    NtagWriteOptions,
    Type2EraseOptions,
    Type2WriteOptions,
    ntag_erase_profile,
    ntag_write_profile,
    type2_erase_profile,
    type2_write_profile,
)
from bambu_rfid_diag.proxmark import ProxmarkRunner


class RefactorContractTests(unittest.TestCase):
    def test_legacy_type2_option_names_are_exact_aliases(self) -> None:
        self.assertIs(NtagWriteOptions, Type2WriteOptions)
        self.assertIs(NtagEraseOptions, Type2EraseOptions)
        self.assertEqual(ntag_write_profile("recommended"), type2_write_profile("recommended"))
        self.assertEqual(ntag_erase_profile("recommended"), type2_erase_profile("recommended"))

    def test_ui_events_have_named_kinds_and_payloads(self) -> None:
        event = UiEvent.live("type2", "command_output", "line")
        self.assertIs(event.kind, UiEventKind.LIVE)
        self.assertEqual(event.mode, "type2")
        self.assertEqual(event.payload, ("command_output", "line"))

    def test_settings_repository_round_trip_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            repository = SettingsRepository(path)
            repository.save({"language": "en", "port": "COM8"})
            self.assertEqual(repository.load(), {"language": "en", "port": "COM8"})
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_settings_repository_rejects_non_mapping_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps(["not", "a", "mapping"]), encoding="utf-8")
            self.assertEqual(SettingsRepository(path).load(), {})

    def test_complete_user_data_directory_can_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                data_root = app_data_directory()
                (data_root / "logs").mkdir(parents=True)
                (data_root / "logs" / "sample.txt").write_text(
                    "sample", encoding="utf-8"
                )
                (data_root / "settings.json").write_text(
                    "{}", encoding="utf-8"
                )
                removed = clear_user_data_directory()
                self.assertEqual(removed, data_root)
                self.assertFalse(data_root.exists())

    def test_pm3_callback_failures_are_recorded_without_breaking_transport(self) -> None:
        layout = SimpleNamespace(root=Path("."), client_dir=Path("."))

        def broken_callback(_event: str, _payload: object) -> None:
            raise RuntimeError("callback failed")

        runner = ProxmarkRunner(layout, on_event=broken_callback)
        with self.assertLogs("bambu_rfid_diag.pm3.session", level="ERROR"):
            runner._emit("command_output", "line")
        self.assertEqual(len(runner.callback_errors), 1)
        self.assertIn("callback failed", runner.callback_errors[0])


    def test_release_version_and_optional_exe_builder_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        build_script = (root / "Build_EXE.bat").read_text(encoding="utf-8")
        helper = (root / "tools" / "build_exe.py").read_text(encoding="utf-8")
        spec = (root / "Bambu_RFID_Writer.spec").read_text(encoding="utf-8")
        self.assertEqual(APP_VERSION, "0.9.3")
        self.assertNotIn("beta", APP_VERSION.lower())
        self.assertIn(".build-tools", build_script)
        self.assertIn("pyinstaller>=6,<7", build_script.lower())
        self.assertIn("tools\\build_exe.py", build_script)
        self.assertIn("Bambu_RFID_Writer.spec", helper)
        self.assertIn("Bambu_RFID_Writer.exe", helper)
        self.assertIn("app_icon.ico", spec)
        self.assertIn("bambu_rfid_diag/assets", spec)
        self.assertIn("bambu_rfid_diag/locales", spec)


if __name__ == "__main__":
    unittest.main()
