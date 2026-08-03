from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from bambu_rfid_diag.infrastructure.material_library_cache import (
    MaterialLibraryCacheRepository,
)
from bambu_rfid_diag.material_library import (
    flatten_sources,
    load_cached_material_library,
    scan_material_library,
    uid_suffix_from_name,
)


class MaterialLibraryTests(unittest.TestCase):
    def test_prunes_hidden_and_non_material_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "README_assets").mkdir()
            source = root / "PETG" / "PETG Basic" / "Black" / "A1B2C3D4"
            source.mkdir(parents=True)
            # Invalid contents are intentional: scanning must use names only.
            (source / "broken-dump.bin").write_bytes(b"bad")

            nodes = scan_material_library(root)
            candidates = flatten_sources(nodes)

        self.assertEqual([node.name for node in nodes], ["PETG"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].uid_hex, "A1B2C3D4")
        self.assertNotIn(".github", [part for node in nodes for part in node.path.parts])

    def test_accepts_uid_only_and_descriptive_uid_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "PLA" / "PLA Basic" / "White" / "768EEACA").mkdir(parents=True)
            (root / "PETG" / "PETGgray0C79DDE0").mkdir(parents=True)

            candidates = flatten_sources(scan_material_library(root))

        self.assertEqual(
            {(node.name, node.uid_hex) for node in candidates},
            {("768EEACA", "768EEACA"), ("PETGgray0C79DDE0", "0C79DDE0")},
        )

    def test_rejects_uid_in_middle_or_missing_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "PLA" / "768EEACA_backup").mkdir(parents=True)
            (root / "ABS" / "not-a-tag").mkdir(parents=True)

            self.assertEqual(scan_material_library(root), [])

    def test_uid_suffix_parser(self) -> None:
        self.assertEqual(uid_suffix_from_name("768EEACA"), "768EEACA")
        self.assertEqual(uid_suffix_from_name("PETGwhite001D075F"), "001D075F")
        self.assertIsNone(uid_suffix_from_name("768EEACA_backup"))
        self.assertEqual(uid_suffix_from_name("A768EEACA"), "768EEACA")

    def test_persistent_cache_restores_without_reading_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "library"
            source = root / "PETG" / "PETG Basic" / "Black" / "A1B2C3D4"
            source.mkdir(parents=True)
            dump = bytearray(1024)
            dump[:5] = bytes.fromhex("A1B2C3D404")
            (source / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
            (source / "hf-mf-A1B2C3D4-key.bin").write_bytes(bytes(192))
            repository = MaterialLibraryCacheRepository(Path(directory) / "cache.json")

            scanned = scan_material_library(
                root,
                cache_repository=repository,
            )
            self.assertEqual(len(flatten_sources(scanned)), 1)

            with mock.patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("binary files must not be read"),
            ):
                restored = load_cached_material_library(
                    root,
                    cache_repository=repository,
                )

        self.assertIsNotNone(restored)
        self.assertEqual(len(flatten_sources(restored or [])), 1)
        self.assertTrue(flatten_sources(restored or [])[0].cached)

    def test_persistent_cache_is_invalidated_when_a_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "library"
            source = root / "PLA" / "PLA Basic" / "White" / "768EEACA"
            source.mkdir(parents=True)
            dump_path = source / "hf-mf-768EEACA-dump.bin"
            dump = bytearray(1024)
            dump[:5] = bytes.fromhex("768EEACA28")
            dump_path.write_bytes(dump)
            (source / "hf-mf-768EEACA-key.bin").write_bytes(bytes(192))
            repository = MaterialLibraryCacheRepository(Path(directory) / "cache.json")

            scan_material_library(root, cache_repository=repository)
            dump_path.write_bytes(bytes(dump) + b"changed")
            restored = load_cached_material_library(
                root,
                cache_repository=repository,
            )

        self.assertIsNone(restored)

    def test_cached_paths_cannot_escape_library_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "library"
            root.mkdir()
            repository = MaterialLibraryCacheRepository(base / "cache.json")
            for malicious in ("../outside", str((base / "outside").resolve())):
                with self.subTest(path=malicious):
                    repository.save(
                        {
                            "schema": 1,
                            "root": str(root),
                            "locale": "cs",
                            "directories": [],
                            "files": [],
                            "nodes": [
                                {
                                    "name": "bad",
                                    "path": malicious,
                                    "children": [],
                                    "status": "unverified",
                                }
                            ],
                        }
                    )
                    self.assertIsNone(
                        load_cached_material_library(
                            root, cache_repository=repository
                        )
                    )


if __name__ == "__main__":
    unittest.main()
