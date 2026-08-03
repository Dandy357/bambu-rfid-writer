from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "bambu_rfid_diag" / "assets"
ICON_ROOT = ASSET_ROOT / "icons"
APP_ASSETS = {
    "app_icon_source.png",
    "app_icon_32.png",
    "app_icon_64.png",
    "app_icon_128.png",
    "app_icon_256.png",
    "app_icon.ico",
}
BASE_NAMES = (
    "settings", "sun", "moon", "chip", "nfc", "write", "erase",
    "diagnostic", "folder", "report", "backup", "plus", "copy",
    "cancel", "chevron_right", "check", "warning", "error", "info",
    "skip", "ready",
)


def expected_paths() -> set[Path]:
    expected: set[Path] = set()
    for variant in ("light", "dark", "inverse"):
        for size in (20, 32):
            for name in BASE_NAMES:
                expected.add(Path(variant) / f"{name}_{size}.png")
    for variant in ("muted_light", "muted_dark"):
        for name in BASE_NAMES:
            expected.add(Path(variant) / f"{name}_20.png")
    for variant, name in (
        ("ok_light", "check"),
        ("ok_dark", "check"),
        ("warning_light", "warning"),
        ("warning_dark", "warning"),
        ("error_light", "error"),
        ("error_dark", "error"),
        ("info_light", "info"),
        ("info_dark", "info"),
        ("skip_light", "skip"),
        ("skip_dark", "skip"),
    ):
        expected.add(Path(variant) / f"{name}_18.png")
    for theme in ("light", "dark"):
        for name in (
            "checkbox_off_18.png",
            "checkbox_on_18.png",
            "checkbox_off_disabled_18.png",
            "checkbox_on_disabled_18.png",
        ):
            expected.add(Path(theme) / name)
    return expected


def main() -> int:
    expected = expected_paths()
    actual = {
        path.relative_to(ICON_ROOT)
        for path in ICON_ROOT.rglob("*.png")
        if path.is_file()
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    missing_app_assets = sorted(
        name for name in APP_ASSETS if not (ASSET_ROOT / name).is_file()
    )
    if missing or unexpected or missing_app_assets:
        print("Icon asset validation failed:", file=sys.stderr)
        for path in missing:
            print(f"- missing: {path}", file=sys.stderr)
        for path in unexpected:
            print(f"- unexpected: {path}", file=sys.stderr)
        for name in missing_app_assets:
            print(f"- missing application asset: {name}", file=sys.stderr)
        return 1
    print(
        f"Icon asset validation passed: {len(actual)} themed PNG files "
        f"and {len(APP_ASSETS)} application icon files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
