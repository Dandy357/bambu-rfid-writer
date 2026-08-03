from __future__ import annotations

import secrets
from pathlib import Path


class OperationWorkspace:
    """Own temporary files staged in the PM3 client working directory."""

    def __init__(self, client_directory: Path, *, token: str | None = None) -> None:
        self.client_directory = client_directory
        self.token = token or secrets.token_hex(6)
        self.names: dict[str, str] = {}
        self.paths: dict[str, Path] = {}

    def reserve(self, key: str, suffix: str) -> Path:
        """Reserve one unique staged filename and return its full path."""
        if key in self.paths:
            raise ValueError(f"Workspace key already exists: {key}")
        name = f"brw_{self.token}_{suffix}"
        path = self.client_directory / name
        self.names[key] = name
        self.paths[key] = path
        return path

    def reserve_many(self, entries: dict[str, str]) -> None:
        """Reserve a group of files keyed by workflow-specific names."""
        for key, suffix in entries.items():
            self.reserve(key, suffix)

    def cleanup(self) -> None:
        """Remove staged binary files and PM3-generated sidecar files."""
        for path in self.paths.values():
            for candidate in (
                path,
                Path(str(path) + ".bin"),
                Path(str(path) + ".json"),
            ):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    # Cleanup must never hide the operation result.
                    continue
