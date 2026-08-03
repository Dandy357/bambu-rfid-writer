from __future__ import annotations

import unittest
from pathlib import Path

from bambu_rfid_diag.ui.theme import DARK, LIGHT, PALETTES


def _relative_luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    converted = [
        value / 12.92
        if value <= 0.03928
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * converted[0] + 0.7152 * converted[1] + 0.0722 * converted[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (high + 0.05) / (low + 0.05)


class ThemeContrastTests(unittest.TestCase):
    def test_primary_text_meets_normal_text_contrast(self) -> None:
        for name in (LIGHT, DARK):
            with self.subTest(theme=name):
                palette = PALETTES[name]
                self.assertGreaterEqual(_contrast(palette.text, palette.window), 7.0)
                self.assertGreaterEqual(_contrast(palette.text, palette.field), 7.0)

    def test_white_button_text_meets_normal_text_contrast(self) -> None:
        for name in (LIGHT, DARK):
            palette = PALETTES[name]
            for role in ("cuid", "type2", "danger"):
                with self.subTest(theme=name, role=role):
                    self.assertGreaterEqual(
                        _contrast("#FFFFFF", getattr(palette, role)), 4.5
                    )

    def test_diagnostic_text_meets_normal_text_contrast(self) -> None:
        for name in (LIGHT, DARK):
            palette = PALETTES[name]
            for role in ("ok", "warning", "error", "info", "skipped"):
                with self.subTest(theme=name, role=role):
                    self.assertGreaterEqual(
                        _contrast(getattr(palette, role), palette.surface), 4.5
                    )


    def test_application_and_settings_icons_are_distinct_assets(self) -> None:
        asset_root = Path(__file__).resolve().parents[1] / "bambu_rfid_diag" / "assets"
        for name in (
            "app_icon_source.png",
            "app_icon_32.png",
            "app_icon_64.png",
            "app_icon_128.png",
            "app_icon_256.png",
            "app_icon.ico",
        ):
            with self.subTest(asset=name):
                self.assertTrue((asset_root / name).is_file())

        settings_icon = asset_root / "icons" / "light" / "settings_32.png"
        sun_icon = asset_root / "icons" / "light" / "sun_32.png"
        self.assertNotEqual(settings_icon.read_bytes(), sun_icon.read_bytes())

    def test_dark_fields_are_not_light_surfaces(self) -> None:
        dark = PALETTES[DARK]
        self.assertNotEqual(dark.field.lower(), "#ffffff")
        self.assertNotEqual(dark.surface.lower(), "#ffffff")
        self.assertNotEqual(dark.field, PALETTES[LIGHT].field)


if __name__ == "__main__":
    unittest.main()
