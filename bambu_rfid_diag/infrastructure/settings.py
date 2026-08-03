from __future__ import annotations

import json
from pathlib import Path

from .paths import app_data_directory


class SettingsRepository:
    """Load and atomically persist the application's string settings map."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_directory() / "settings.json")

    def load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in data.items()
            if value is not None
        }

    def save(self, settings: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def settings_path() -> Path:
    return SettingsRepository().path


def load_settings() -> dict[str, str]:
    return SettingsRepository().load()


def save_settings(settings: dict[str, str]) -> None:
    SettingsRepository().save(settings)
