from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bambu_rfid_diag.ui.settings_view import SettingsViewMixin


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class SettingsPersistenceTests(unittest.TestCase):
    def _dummy(self):
        errors: list[tuple[str, str]] = []
        dummy = SimpleNamespace(
            _current_settings_values=lambda: {"language": "cs"},
            t=lambda key, **kwargs: (
                "Save failed" if key.endswith("title") else f"Save failed: {kwargs.get('error', '')}"
            ),
            settings_status_var=_Status(),
            dialogs=SimpleNamespace(error=lambda title, message: errors.append((title, message))),
        )
        return dummy, errors

    def test_save_failure_is_visible_and_returns_false(self) -> None:
        dummy, errors = self._dummy()
        with self.assertLogs(
            "bambu_rfid_diag.ui.settings_view",
            level="ERROR",
        ), patch(
            "bambu_rfid_diag.ui.settings_view.save_settings",
            side_effect=OSError("disk full"),
        ):
            saved = SettingsViewMixin._save_current_settings(
                dummy,
                show_error=True,
            )
        self.assertFalse(saved)
        self.assertIn("disk full", dummy.settings_status_var.value)
        self.assertEqual(len(errors), 1)

    def test_successful_save_returns_true(self) -> None:
        dummy, errors = self._dummy()
        with patch("bambu_rfid_diag.ui.settings_view.save_settings") as save:
            saved = SettingsViewMixin._save_current_settings(
                dummy, show_error=True
            )
        self.assertTrue(saved)
        save.assert_called_once_with({"language": "cs"})
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
