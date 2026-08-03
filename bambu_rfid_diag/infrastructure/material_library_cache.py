from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import app_data_directory


class MaterialLibraryCacheRepository:
    """Persist the last material-library snapshot as an atomic JSON document."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_directory() / "material_library_cache.json")

    def load(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return
