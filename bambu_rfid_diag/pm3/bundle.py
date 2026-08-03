from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..i18n import Translator, available_locales, normalize_locale
from .errors import BundleValidationError, UnsafeCommandError


ALLOWED_COMMANDS = frozenset(
    {
        "hw version",
        "hf 14a info",
        "hf mf info",
        "hf mf chk --1k -k FFFFFFFFFFFF --no-default",
        "hf mfu info",
        "hf mfu rdbl -b 130",
        "hf mfu rdbl -b 131",
    }
)


@dataclass(frozen=True, slots=True)
class BundleLayout:
    """Resolved filesystem layout of an RRG/Iceman Windows bundle."""

    root: Path
    pm3_bat: Path
    client_dir: Path
    setup_bat: Path
    pm3_script: Path
    proxmark_exe: Path


def normalize_bundle_root(selected: str | os.PathLike[str]) -> Path:
    """Normalize a selected root, ``pm3.bat``, or client directory."""
    path = Path(selected).expanduser()
    if path.is_file() and path.name.lower() == "pm3.bat":
        path = path.parent
    if path.name.lower() == "client" and (path / "setup.bat").is_file():
        path = path.parent
    return path.resolve()


def resolve_bundle(
    selected: str | os.PathLike[str], locale: str = "en"
) -> BundleLayout:
    """Validate and return the exact files required to launch PM3."""
    tr = Translator(normalize_locale(locale))
    root = normalize_bundle_root(selected)
    layout = BundleLayout(
        root=root,
        pm3_bat=root / "pm3.bat",
        client_dir=root / "client",
        setup_bat=root / "client" / "setup.bat",
        pm3_script=root / "client" / "pm3",
        proxmark_exe=root / "client" / "proxmark3.exe",
    )
    expected_paths = (
        (layout.pm3_bat, "file"),
        (layout.client_dir, "directory"),
        (layout.setup_bat, "file"),
        (layout.pm3_script, "file"),
        (layout.proxmark_exe, "file"),
    )
    missing = [
        path.relative_to(root).as_posix()
        for path, expected_type in expected_paths
        if (expected_type == "file" and not path.is_file())
        or (expected_type == "directory" and not path.is_dir())
    ]
    if missing:
        raise BundleValidationError(
            tr.t("bundle.incomplete", missing=", ".join(missing))
        )

    try:
        bat_text = layout.pm3_bat.read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
    except OSError as exc:
        raise BundleValidationError(tr.t("bundle.read_pm3", error=exc)) from exc
    if "setup.bat" not in bat_text or "bash pm3" not in bat_text:
        raise BundleValidationError(tr.t("bundle.invalid_pm3"))
    return layout


def is_auto_port(port: str | None) -> bool:
    """Return whether a stored or localized value means automatic detection."""

    if port is None or not str(port).strip():
        return True
    normalized = str(port).strip().casefold()
    aliases = {
        "auto",
        "automatic",
        "automatic detection",
        "automatically",
        "automaticky",
        "automatická detekce",
    }
    for locale_code in available_locales():
        aliases.add(Translator(locale_code).t("common.auto").strip().casefold())
    return normalized in aliases


def validate_port(port: str | None, locale: str = "en") -> str | None:
    """Validate an optional Windows COM port without accepting shell syntax."""
    if is_auto_port(port):
        return None
    normalized = str(port).strip().upper()
    if not re.fullmatch(r"COM(?:[1-9]|[1-9][0-9]{1,2})", normalized):
        raise ValueError(
            Translator(normalize_locale(locale)).t("validation.port_format")
        )
    return normalized


def validate_read_only_command(command: str, locale: str = "en") -> str:
    """Allow only the fixed read-only diagnostics exposed by the application."""
    atoms = [part.strip() for part in command.split(";") if part.strip()]
    if not atoms or any(atom not in ALLOWED_COMMANDS for atom in atoms):
        raise UnsafeCommandError(
            Translator(normalize_locale(locale)).t(
                "proxmark.unsafe_read_command"
            )
        )
    return "; ".join(atoms)


def batch_quote(path: Path, locale: str = "en") -> str:
    """Quote a Windows batch path while rejecting expansion metacharacters."""
    value = str(path)
    if any(char in value for char in ('"', "%", "\r", "\n")):
        raise BundleValidationError(
            Translator(normalize_locale(locale)).t(
                "proxmark.unsupported_bundle_character"
            )
        )
    return f'"{value}"'


def validate_internal_command(command: str, translator: Translator) -> None:
    """Reject control characters and shell metacharacters in trusted commands."""
    if not command.strip() or any(
        character in command
        for character in (
            '"',
            "\r",
            "\n",
            "&",
            "|",
            "<",
            ">",
            "%",
            "!",
            "^",
            "`",
            "$",
        )
    ):
        raise UnsafeCommandError(
            translator.t("proxmark.unsafe_internal_command")
        )


def make_runner_batch(
    layout: BundleLayout,
    command: str,
    port: str | None,
    locale: str = "en",
) -> str:
    """Build the backward-compatible one-shot diagnostic batch file."""
    command = validate_read_only_command(command, locale)
    return make_runner_batch_trusted(layout, command, port, locale)


def make_runner_batch_trusted(
    layout: BundleLayout,
    command: str,
    port: str | None,
    locale: str = "en",
) -> str:
    tr = Translator(normalize_locale(locale))
    port = validate_port(port, locale)
    validate_internal_command(command, tr)
    port_args = f" -p {port}" if port else ""
    return "\r\n".join(
        [
            "@echo off",
            "setlocal EnableExtensions DisableDelayedExpansion",
            f"cd /d {batch_quote(layout.client_dir, locale)}",
            f"call {batch_quote(layout.setup_bat, locale)}",
            "if errorlevel 1 (",
            "  echo [BRW-ERROR] setup.bat failed.",
            "  exit /b 90",
            ")",
            f'bash pm3{port_args} --incognito -c "{command}"',
            'set "BRW_EXIT=%ERRORLEVEL%"',
            "exit /b %BRW_EXIT%",
            "",
        ]
    )


def make_session_batch(
    layout: BundleLayout,
    port: str | None,
    locale: str = "en",
) -> str:
    """Build the batch file that starts one persistent interactive PM3 client."""
    port = validate_port(port, locale)
    port_args = f" -p {port}" if port else ""
    return "\r\n".join(
        [
            "@echo off",
            "setlocal EnableExtensions DisableDelayedExpansion",
            f"cd /d {batch_quote(layout.client_dir, locale)}",
            f"call {batch_quote(layout.setup_bat, locale)}",
            "if errorlevel 1 (",
            "  echo [BRW-ERROR] setup.bat failed.",
            "  exit /b 90",
            ")",
            f"bash pm3{port_args} --incognito",
            'set "BRW_EXIT=%ERRORLEVEL%"',
            "exit /b %BRW_EXIT%",
            "",
        ]
    )
