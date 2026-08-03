from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .i18n import Translator, normalize_locale
from .infrastructure.material_library_cache import MaterialLibraryCacheRepository


IGNORED_DIRECTORY_NAMES = {".git", ".github", "__pycache__", "node_modules"}
_UID_SUFFIX_RE = re.compile(r"(?i)([0-9a-f]{8})$")
_UID_TOKEN_RE = re.compile(r"(?i)(?<![0-9a-f])([0-9a-f]{8})(?![0-9a-f])")
_CACHE_SCHEMA = 1

STATUS_READY = "ready"
STATUS_WARNING = "warning"
STATUS_INVALID = "invalid"
STATUS_UNVERIFIED = "unverified"


@dataclass(slots=True)
class MaterialNode:
    name: str
    path: Path
    children: list["MaterialNode"] = field(default_factory=list)
    uid_hex: str | None = None
    dump_uid_hex: str | None = None
    dump_path: Path | None = None
    key_path: Path | None = None
    status: str = STATUS_UNVERIFIED
    detail: str = ""
    cached: bool = False

    @property
    def is_source(self) -> bool:
        return self.uid_hex is not None

    @property
    def authoritative_uid(self) -> str | None:
        return self.dump_uid_hex or self.uid_hex


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    signature: tuple[tuple[str, int, int], ...]
    dump_uid_hex: str | None
    dump_path: Path | None
    key_path: Path | None
    status: str
    detail: str


@dataclass(slots=True)
class _ScanTracker:
    root: Path
    directories: dict[str, int] = field(default_factory=dict)
    files: dict[str, tuple[int, int]] = field(default_factory=dict)

    def record_directory(self, path: Path) -> None:
        stat = path.stat()
        self.directories[_relative_key(self.root, path)] = int(stat.st_mtime_ns)

    def record_file(self, path: Path, size: int, mtime_ns: int) -> None:
        self.files[_relative_key(self.root, path)] = (int(size), int(mtime_ns))


_QUICK_CACHE: dict[tuple[Path, str], _CacheEntry] = {}


def uid_suffix_from_name(name: str) -> str | None:
    match = _UID_SUFFIX_RE.search(name.strip())
    return match.group(1).upper() if match else None


def _relative_key(root: Path, path: Path) -> str:
    if path == root:
        return "."
    return path.relative_to(root).as_posix()


def _resolve_relative(root: Path, value: str) -> Path:
    """Resolve a cached relative path without allowing escape from the library root."""

    candidate_value = Path(value)
    if candidate_value.is_absolute():
        raise ValueError("Cached material-library paths must be relative")
    candidate = (root if value == "." else root.joinpath(*candidate_value.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Cached material-library path escapes its root") from exc
    return candidate


def _is_ignored_name(name: str) -> bool:
    return name.startswith(".") or name.lower() in IGNORED_DIRECTORY_NAMES


def _child_directories(path: Path, tracker: _ScanTracker | None = None) -> list[Path]:
    if tracker is not None:
        tracker.record_directory(path)
    children: list[Path] = []
    with os.scandir(path) as entries:
        for entry in entries:
            if _is_ignored_name(entry.name):
                continue
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_directory:
                children.append(Path(entry.path))
    children.sort(key=lambda child: child.name.casefold())
    return children


def _candidate_files(
    path: Path,
    tracker: _ScanTracker | None = None,
) -> tuple[list[Path], tuple[tuple[str, int, int], ...]]:
    if tracker is not None:
        tracker.record_directory(path)
    files: list[Path] = []
    signature: list[tuple[str, int, int]] = []
    with os.scandir(path) as entries:
        for entry in entries:
            try:
                is_binary_file = entry.name.lower().endswith(".bin")
                if not entry.is_file(follow_symlinks=False) or not is_binary_file:
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            file_path = Path(entry.path)
            size = int(stat.st_size)
            mtime_ns = int(stat.st_mtime_ns)
            files.append(file_path)
            signature.append((entry.name, size, mtime_ns))
            if tracker is not None:
                tracker.record_file(file_path, size, mtime_ns)
    files.sort(key=lambda item: item.name.casefold())
    signature.sort(key=lambda item: item[0].casefold())
    return files, tuple(signature)


def _quick_inspect(
    path: Path,
    folder_uid: str,
    locale: str,
    tracker: _ScanTracker | None = None,
) -> _CacheEntry:
    normalized_locale = normalize_locale(locale)
    t = Translator(normalized_locale).t
    try:
        files, signature = _candidate_files(path, tracker)
    except OSError as exc:
        return _CacheEntry(
            (),
            None,
            None,
            None,
            STATUS_UNVERIFIED,
            t("library.quick_read_failed", error=exc),
        )

    cache_key = (path, normalized_locale)
    cached = _QUICK_CACHE.get(cache_key)
    if cached is not None and cached.signature == signature:
        return cached

    dump_candidates = [
        item
        for item in files
        if "dump" in item.stem.lower()
        and not item.stem.lower().startswith("bambu_verify_")
    ]
    key_candidates = [item for item in files if "key" in item.stem.lower()]
    if len(dump_candidates) != 1 or len(key_candidates) != 1:
        detail = t(
            "library.quick_pair_count",
            dumps=len(dump_candidates),
            keys=len(key_candidates),
        )
        entry = _CacheEntry(
            signature,
            None,
            dump_candidates[0] if len(dump_candidates) == 1 else None,
            key_candidates[0] if len(key_candidates) == 1 else None,
            STATUS_INVALID,
            detail,
        )
        _QUICK_CACHE[cache_key] = entry
        return entry

    dump_path = dump_candidates[0]
    key_path = key_candidates[0]
    try:
        dump_data = dump_path.read_bytes()
        key_data = key_path.read_bytes()
    except OSError as exc:
        entry = _CacheEntry(
            signature,
            None,
            dump_path,
            key_path,
            STATUS_UNVERIFIED,
            t("library.quick_read_failed", error=exc),
        )
        _QUICK_CACHE[cache_key] = entry
        return entry

    problems: list[str] = []
    warnings: list[str] = []
    if len(dump_data) != 1024:
        problems.append(t("library.quick_dump_size", bytes=len(dump_data)))
    if len(key_data) != 192:
        problems.append(t("library.quick_key_size", bytes=len(key_data)))

    dump_uid = dump_data[:4].hex().upper() if len(dump_data) >= 4 else None
    if len(dump_data) >= 5:
        expected_bcc = dump_data[0] ^ dump_data[1] ^ dump_data[2] ^ dump_data[3]
        if dump_data[4] != expected_bcc:
            problems.append(t("library.quick_bcc"))
    elif dump_data:
        problems.append(t("library.quick_bcc"))

    if dump_uid and folder_uid != dump_uid:
        warnings.append(
            t("library.quick_folder_uid", folder=folder_uid, dump=dump_uid)
        )
    for file_path in (dump_path, key_path):
        tokens = {
            match.group(1).upper()
            for match in _UID_TOKEN_RE.finditer(file_path.stem)
        }
        if dump_uid and tokens and any(token != dump_uid for token in tokens):
            warnings.append(
                t(
                    "library.quick_filename_uid",
                    file=file_path.name,
                    dump=dump_uid,
                )
            )

    if problems:
        status = STATUS_INVALID
        detail = "; ".join(problems + warnings)
    elif warnings:
        status = STATUS_WARNING
        detail = "; ".join(warnings)
    else:
        status = STATUS_READY
        detail = t("library.quick_ready", uid=dump_uid or folder_uid)
    entry = _CacheEntry(
        signature,
        dump_uid,
        dump_path,
        key_path,
        status,
        detail,
    )
    _QUICK_CACHE[cache_key] = entry
    return entry


def _scan_directory(
    path: Path,
    locale: str,
    tracker: _ScanTracker,
) -> MaterialNode | None:
    uid_hex = uid_suffix_from_name(path.name)
    if uid_hex is not None:
        result = _quick_inspect(path, uid_hex, locale, tracker)
        return MaterialNode(
            name=path.name,
            path=path,
            uid_hex=uid_hex,
            dump_uid_hex=result.dump_uid_hex,
            dump_path=result.dump_path,
            key_path=result.key_path,
            status=result.status,
            detail=result.detail,
        )

    try:
        child_paths = _child_directories(path, tracker)
    except OSError:
        return None
    children = [
        child
        for child_path in child_paths
        if (child := _scan_directory(child_path, locale, tracker)) is not None
    ]
    if not children:
        return None
    return MaterialNode(name=path.name, path=path, children=children)


def _serialize_node(node: MaterialNode, root: Path) -> dict[str, Any]:
    return {
        "name": node.name,
        "path": _relative_key(root, node.path),
        "children": [_serialize_node(child, root) for child in node.children],
        "uid_hex": node.uid_hex,
        "dump_uid_hex": node.dump_uid_hex,
        "dump_path": _relative_key(root, node.dump_path) if node.dump_path else None,
        "key_path": _relative_key(root, node.key_path) if node.key_path else None,
        "status": node.status,
        "detail": node.detail,
    }


def _deserialize_node(data: dict[str, Any], root: Path, locale_matches: bool) -> MaterialNode:
    status = str(data.get("status", STATUS_UNVERIFIED))
    uid_hex = data.get("uid_hex")
    dump_uid_hex = data.get("dump_uid_hex")
    detail = str(data.get("detail", "")) if locale_matches else ""
    return MaterialNode(
        name=str(data.get("name", "")),
        path=_resolve_relative(root, str(data.get("path", "."))),
        children=[
            _deserialize_node(child, root, locale_matches)
            for child in data.get("children", [])
            if isinstance(child, dict)
        ],
        uid_hex=str(uid_hex) if uid_hex else None,
        dump_uid_hex=str(dump_uid_hex) if dump_uid_hex else None,
        dump_path=(
            _resolve_relative(root, str(data["dump_path"]))
            if data.get("dump_path")
            else None
        ),
        key_path=(
            _resolve_relative(root, str(data["key_path"]))
            if data.get("key_path")
            else None
        ),
        status=status,
        detail=detail,
        cached=True,
    )


def _cache_payload(
    root: Path,
    locale: str,
    nodes: list[MaterialNode],
    tracker: _ScanTracker,
) -> dict[str, Any]:
    return {
        "schema": _CACHE_SCHEMA,
        "root": str(root),
        "locale": normalize_locale(locale),
        "directories": [
            {"path": path, "mtime_ns": mtime_ns}
            for path, mtime_ns in sorted(tracker.directories.items())
        ],
        "files": [
            {"path": path, "size": size, "mtime_ns": mtime_ns}
            for path, (size, mtime_ns) in sorted(tracker.files.items())
        ],
        "nodes": [_serialize_node(node, root) for node in nodes],
    }


def _cache_is_current(payload: dict[str, Any], root: Path) -> bool:
    if payload.get("schema") != _CACHE_SCHEMA:
        return False
    try:
        cached_root = Path(str(payload.get("root", ""))).expanduser().resolve()
    except OSError:
        return False
    if cached_root != root:
        return False
    try:
        for item in payload.get("directories", []):
            path = _resolve_relative(root, str(item["path"]))
            stat = path.stat()
            if not path.is_dir() or int(stat.st_mtime_ns) != int(item["mtime_ns"]):
                return False
        for item in payload.get("files", []):
            path = _resolve_relative(root, str(item["path"]))
            stat = path.stat()
            if (
                not path.is_file()
                or int(stat.st_size) != int(item["size"])
                or int(stat.st_mtime_ns) != int(item["mtime_ns"])
            ):
                return False
    except (OSError, KeyError, TypeError, ValueError):
        return False
    return True


def scan_material_library(
    root: str | Path,
    locale: str = "en",
    *,
    cache_repository: MaterialLibraryCacheRepository | None = None,
) -> list[MaterialNode]:
    root_path = Path(root).expanduser().resolve()
    t = Translator(normalize_locale(locale)).t
    if not root_path.is_dir():
        raise ValueError(t("library.not_directory"))
    tracker = _ScanTracker(root_path)
    try:
        child_paths = _child_directories(root_path, tracker)
    except OSError as exc:
        raise ValueError(t("library.read_failed", error=exc)) from exc
    nodes = [
        child
        for child_path in child_paths
        if (child := _scan_directory(child_path, locale, tracker)) is not None
    ]
    duplicates: dict[str, list[MaterialNode]] = {}
    for node in flatten_sources(nodes):
        uid = node.authoritative_uid
        if uid and node.status in {STATUS_READY, STATUS_WARNING}:
            duplicates.setdefault(uid, []).append(node)
    for uid, matches in duplicates.items():
        if len(matches) < 2:
            continue
        warning = t("library.quick_duplicate_uid", uid=uid, count=len(matches))
        for node in matches:
            node.status = STATUS_WARNING
            node.detail = f"{node.detail}; {warning}" if node.detail else warning

    repository = cache_repository or MaterialLibraryCacheRepository()
    try:
        repository.save(_cache_payload(root_path, locale, nodes, tracker))
    except OSError:
        pass
    return nodes


def load_cached_material_library(
    root: str | Path,
    locale: str = "en",
    *,
    cache_repository: MaterialLibraryCacheRepository | None = None,
) -> list[MaterialNode] | None:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        return None
    repository = cache_repository or MaterialLibraryCacheRepository()
    payload = repository.load()
    if payload is None or not _cache_is_current(payload, root_path):
        return None
    cached_locale = normalize_locale(str(payload.get("locale", "cs")))
    locale_matches = cached_locale == normalize_locale(locale)
    raw_nodes = payload.get("nodes", [])
    if not isinstance(raw_nodes, list):
        return None
    try:
        return [
            _deserialize_node(item, root_path, locale_matches)
            for item in raw_nodes
            if isinstance(item, dict)
        ]
    except (KeyError, TypeError, ValueError):
        return None


def clear_material_library_cache(
    cache_repository: MaterialLibraryCacheRepository | None = None,
) -> None:
    (cache_repository or MaterialLibraryCacheRepository()).clear()


def refresh_material_node(node: MaterialNode, locale: str = "en") -> MaterialNode:
    if not node.is_source or node.uid_hex is None:
        return node
    result = _quick_inspect(node.path, node.uid_hex, locale)
    node.dump_uid_hex = result.dump_uid_hex
    node.dump_path = result.dump_path
    node.key_path = result.key_path
    node.status = result.status
    node.detail = result.detail
    node.cached = False
    return node


def flatten_sources(nodes: list[MaterialNode]) -> list[MaterialNode]:
    result: list[MaterialNode] = []
    for node in nodes:
        if node.is_source:
            result.append(node)
        result.extend(flatten_sources(node.children))
    return result


def uid_index(nodes: list[MaterialNode]) -> dict[str, list[MaterialNode]]:
    result: dict[str, list[MaterialNode]] = {}
    for node in flatten_sources(nodes):
        uid = node.authoritative_uid
        if uid and node.status in {STATUS_READY, STATUS_WARNING}:
            result.setdefault(uid, []).append(node)
    return result
