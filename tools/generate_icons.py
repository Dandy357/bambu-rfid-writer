from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "bambu_rfid_diag" / "assets" / "icons"
APP_ICON_SOURCE = ROOT / "bambu_rfid_diag" / "assets" / "app_icon_source.png"
BASE = 24.0


class Scheme(dict):
    @property
    def outline(self) -> str:
        return self["outline"]

    @property
    def accent(self) -> str:
        return self["accent"]

    @property
    def accent_soft(self) -> str:
        return self.get("accent_soft", self["accent"])

    @property
    def ok(self) -> str:
        return self.get("ok", "#22C55E")

    @property
    def warning(self) -> str:
        return self.get("warning", "#F59E0B")

    @property
    def error(self) -> str:
        return self.get("error", "#EF4444")

    @property
    def info(self) -> str:
        return self.get("info", self["accent"])


# Geometry helpers -----------------------------------------------------------


def _u(scale: float, value: float) -> int:
    return round(value * scale)


def _line(
    draw: ImageDraw.ImageDraw,
    scale: float,
    points,
    fill: str,
    width: int,
) -> None:
    draw.line(
        [(_u(scale, x), _u(scale, y)) for x, y in points],
        fill=fill,
        width=width,
        joint="curve",
    )


def _rect(
    draw: ImageDraw.ImageDraw,
    scale: float,
    box,
    *,
    radius: float = 0.0,
    outline: str,
    width: int,
    fill=None,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(
        (_u(scale, x1), _u(scale, y1), _u(scale, x2), _u(scale, y2)),
        radius=_u(scale, radius),
        outline=outline,
        width=width,
        fill=fill,
    )


def _ellipse(
    draw: ImageDraw.ImageDraw,
    scale: float,
    box,
    *,
    outline=None,
    width: int = 1,
    fill=None,
) -> None:
    x1, y1, x2, y2 = box
    draw.ellipse(
        (_u(scale, x1), _u(scale, y1), _u(scale, x2), _u(scale, y2)),
        outline=outline,
        width=width,
        fill=fill,
    )


def _arc(
    draw: ImageDraw.ImageDraw,
    scale: float,
    box,
    *,
    start: float,
    end: float,
    fill: str,
    width: int,
) -> None:
    x1, y1, x2, y2 = box
    draw.arc(
        (_u(scale, x1), _u(scale, y1), _u(scale, x2), _u(scale, y2)),
        start=start,
        end=end,
        fill=fill,
        width=width,
    )


def _polygon(
    draw: ImageDraw.ImageDraw,
    scale: float,
    points,
    *,
    outline: str,
    width: int,
    fill=None,
) -> None:
    pts = [(_u(scale, x), _u(scale, y)) for x, y in points]
    draw.polygon(pts, outline=outline, fill=fill)
    if width > 1:
        _line(draw, scale, points + [points[0]], fill=outline, width=width)


# Base shapes ----------------------------------------------------------------


def _gear_points(scale: float) -> list[tuple[int, int]]:
    cx = cy = _u(scale, 12)
    outer, inner = 9.2, 7.1
    pts: list[tuple[int, int]] = []
    for i in range(16):
        angle = math.radians(i * 22.5 - 90)
        radius = outer if i % 2 == 0 else inner
        pts.append(
            (
                cx + round(math.cos(angle) * _u(scale, radius)),
                cy + round(math.sin(angle) * _u(scale, radius)),
            )
        )
    return pts


# Icon drawing functions -----------------------------------------------------


def _draw_folder(draw, scale, scheme: Scheme, width: int) -> None:
    _rect(
        draw,
        scale,
        (3.5, 6.2, 19.5, 12.7),
        radius=1.9,
        outline=scheme.outline,
        width=width,
    )
    _rect(
        draw,
        scale,
        (2.5, 9.2, 21.5, 20.8),
        radius=2.2,
        outline=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(7.3, 14.2), (15.8, 14.2)], fill=scheme.accent, width=width)
    _line(
        draw,
        scale,
        [(7.3, 17.2), (13.6, 17.2)],
        fill=scheme.outline,
        width=max(1, width - 1),
    )


def _draw_tag(draw, scale, scheme: Scheme, width: int) -> None:
    pts = [
        (6.2, 5.0),
        (19.2, 5.0),
        (21.5, 7.3),
        (21.5, 16.8),
        (16.8, 21.5),
        (7.2, 21.5),
        (4.9, 19.2),
        (4.9, 6.2),
    ]
    _polygon(draw, scale, pts, outline=scheme.outline, width=width)
    _ellipse(
        draw,
        scale,
        (16.7, 6.9, 19.4, 9.6),
        outline=scheme.outline,
        width=width,
    )
    _line(
        draw,
        scale,
        [(8.0, 15.8), (12.0, 11.8), (14.6, 14.4)],
        fill=scheme.accent,
        width=width,
    )
    _line(
        draw,
        scale,
        [(10.0, 17.7), (14.2, 13.5), (16.0, 15.3)],
        fill=scheme.accent,
        width=max(1, width - 1),
    )


def _draw_nfc(draw, scale, scheme: Scheme, width: int) -> None:
    _rect(
        draw,
        scale,
        (4.0, 4.0, 20.0, 20.0),
        radius=3.0,
        outline=scheme.outline,
        width=width,
    )
    _line(
        draw,
        scale,
        [(8.0, 16.5), (8.0, 8.5), (15.8, 16.5), (15.8, 8.5)],
        fill=scheme.accent,
        width=width,
    )
    _arc(
        draw,
        scale,
        (12.0, 4.6, 21.0, 13.6),
        start=210,
        end=340,
        fill=scheme.accent,
        width=width,
    )
    _arc(
        draw,
        scale,
        (13.8, 6.4, 19.2, 11.8),
        start=210,
        end=340,
        fill=scheme.accent,
        width=max(1, width - 1),
    )


def _draw_settings(draw, scale, scheme: Scheme, width: int) -> None:
    gear_points = _gear_points(scale)
    draw.polygon(gear_points, outline=scheme.outline)
    draw.line(
        gear_points + [gear_points[0]],
        fill=scheme.outline,
        width=width,
        joint="curve",
    )
    _ellipse(
        draw,
        scale,
        (8.0, 8.0, 16.0, 16.0),
        outline=scheme.accent,
        width=width,
    )


def _draw_diagnostic(draw, scale, scheme: Scheme, width: int) -> None:
    _rect(
        draw,
        scale,
        (3.5, 5.0, 20.5, 16.8),
        radius=2.0,
        outline=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(8.2, 19.0), (15.8, 19.0)], fill=scheme.outline, width=width)
    _line(draw, scale, [(12.0, 16.8), (12.0, 19.0)], fill=scheme.outline, width=width)
    _line(
        draw,
        scale,
        [
            (6.2, 11.2),
            (9.0, 11.2),
            (10.6, 7.8),
            (13.1, 14.2),
            (15.3, 10.0),
            (18.2, 10.0),
        ],
        fill=scheme.accent,
        width=width,
    )


def _draw_write(draw, scale, scheme: Scheme, width: int) -> None:
    _line(
        draw,
        scale,
        [(5.2, 18.8), (9.2, 14.8), (18.4, 5.6)],
        fill=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(14.8, 5.0), (19.0, 9.2)], fill=scheme.outline, width=width)
    _line(
        draw,
        scale,
        [(5.2, 18.8), (7.8, 18.0), (6.0, 16.2)],
        fill=scheme.outline,
        width=width,
    )
    _arc(
        draw,
        scale,
        (12.0, 7.0, 22.0, 17.0),
        start=285,
        end=15,
        fill=scheme.accent,
        width=width,
    )
    _arc(
        draw,
        scale,
        (13.6, 8.8, 19.8, 15.0),
        start=285,
        end=15,
        fill=scheme.accent,
        width=max(1, width - 1),
    )
    _line(
        draw,
        scale,
        [(7.2, 20.5), (16.0, 20.5)],
        fill=scheme.outline,
        width=max(1, width - 1),
    )


def _draw_erase(draw, scale, scheme: Scheme, width: int) -> None:
    pts = [(7.0, 15.4), (12.6, 9.8), (18.8, 16.0), (13.2, 21.4)]
    _polygon(draw, scale, pts, outline=scheme.outline, width=width)
    _line(
        draw,
        scale,
        [(10.2, 18.4), (15.8, 12.8)],
        fill=scheme.accent,
        width=max(1, width - 1),
    )
    for x, y in ((18.3, 18.8), (20.0, 17.7), (21.1, 19.5)):
        _ellipse(draw, scale, (x - 0.4, y - 0.4, x + 0.4, y + 0.4), fill=scheme.outline)


def _draw_backup(draw, scale, scheme: Scheme, width: int) -> None:
    for y in (5.0, 9.4, 13.8):
        _ellipse(
            draw,
            scale,
            (4.8, y, 15.8, y + 3.6),
            outline=scheme.outline,
            width=width,
        )
    _line(draw, scale, [(4.8, 6.8), (4.8, 15.6)], fill=scheme.outline, width=width)
    _line(draw, scale, [(15.8, 6.8), (15.8, 13.9)], fill=scheme.outline, width=width)
    _arc(
        draw,
        scale,
        (12.2, 10.2, 22.0, 20.0),
        start=210,
        end=20,
        fill=scheme.accent,
        width=width,
    )
    _line(
        draw,
        scale,
        [(19.0, 16.1), (20.9, 16.1), (20.0, 18.0)],
        fill=scheme.accent,
        width=max(1, width - 1),
    )


def _draw_report(draw, scale, scheme: Scheme, width: int) -> None:
    _rect(
        draw,
        scale,
        (5.2, 3.8, 18.6, 20.6),
        radius=1.8,
        outline=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(14.0, 3.8), (18.6, 8.4)], fill=scheme.outline, width=width)
    _line(draw, scale, [(7.8, 16.8), (7.8, 13.0)], fill=scheme.accent, width=width)
    _line(draw, scale, [(10.8, 16.8), (10.8, 11.2)], fill=scheme.accent, width=width)
    _line(draw, scale, [(13.8, 16.8), (13.8, 9.4)], fill=scheme.accent, width=width)


def _draw_copy(draw, scale, scheme: Scheme, width: int) -> None:
    _rect(
        draw,
        scale,
        (8.0, 5.6, 18.2, 18.6),
        radius=1.8,
        outline=scheme.outline,
        width=width,
    )
    _rect(
        draw,
        scale,
        (5.4, 8.2, 15.6, 21.2),
        radius=1.8,
        outline=scheme.outline,
        width=width,
    )
    _line(
        draw,
        scale,
        [(8.3, 12.4), (12.8, 12.4)],
        fill=scheme.accent,
        width=max(1, width - 1),
    )
    _line(
        draw,
        scale,
        [(8.3, 15.6), (13.8, 15.6)],
        fill=scheme.outline,
        width=max(1, width - 1),
    )


def _draw_plus(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(
        draw,
        scale,
        (3.2, 3.2, 20.8, 20.8),
        outline=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(12.0, 7.2), (12.0, 16.8)], fill=scheme.accent, width=width)
    _line(draw, scale, [(7.2, 12.0), (16.8, 12.0)], fill=scheme.accent, width=width)


def _draw_cancel(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(
        draw,
        scale,
        (3.2, 3.2, 20.8, 20.8),
        outline=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(8.0, 8.0), (16.0, 16.0)], fill=scheme.outline, width=width)
    _line(draw, scale, [(16.0, 8.0), (8.0, 16.0)], fill=scheme.outline, width=width)


def _draw_check(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(
        draw,
        scale,
        (3.2, 3.2, 20.8, 20.8),
        outline=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(7.0, 12.3), (10.2, 15.6), (17.0, 8.6)], fill=scheme.ok, width=width)


def _draw_warning(draw, scale, scheme: Scheme, width: int) -> None:
    pts = [(12.0, 3.6), (21.0, 19.4), (3.0, 19.4)]
    _polygon(draw, scale, pts, outline=scheme.warning, width=width)
    _line(draw, scale, [(12.0, 8.6), (12.0, 13.2)], fill=scheme.warning, width=width)
    _ellipse(draw, scale, (11.0, 15.2, 13.0, 17.2), fill=scheme.warning)


def _draw_error(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(draw, scale, (3.2, 3.2, 20.8, 20.8), outline=scheme.error, width=width)
    _line(draw, scale, [(12.0, 7.0), (12.0, 13.4)], fill=scheme.error, width=width)
    _ellipse(draw, scale, (11.0, 15.4, 13.0, 17.4), fill=scheme.error)


def _draw_info(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(draw, scale, (3.2, 3.2, 20.8, 20.8), outline=scheme.info, width=width)
    _line(draw, scale, [(12.0, 10.2), (12.0, 16.4)], fill=scheme.info, width=width)
    _ellipse(draw, scale, (11.0, 6.2, 13.0, 8.2), fill=scheme.info)


def _draw_skip(draw, scale, scheme: Scheme, width: int) -> None:
    _line(draw, scale, [(7.0, 7.0), (12.4, 12.0), (7.0, 17.0)], fill=scheme.outline, width=width)
    _line(
        draw,
        scale,
        [(12.4, 7.0), (17.8, 12.0), (12.4, 17.0)],
        fill=scheme.outline,
        width=width,
    )
    _line(draw, scale, [(20.0, 7.2), (20.0, 16.8)], fill=scheme.outline, width=width)


def _draw_ready(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(draw, scale, (3.8, 3.8, 20.2, 20.2), outline=scheme.ok, width=width)
    _ellipse(draw, scale, (9.2, 9.2, 14.8, 14.8), fill=scheme.ok)


def _draw_chevron(draw, scale, scheme: Scheme, width: int) -> None:
    _line(draw, scale, [(8.4, 6.2), (15.4, 12.0), (8.4, 17.8)], fill=scheme.outline, width=width)


def _draw_sun(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(draw, scale, (7.0, 7.0, 17.0, 17.0), outline=scheme.accent, width=width)
    rays = [
        ((12.0, 2.8), (12.0, 5.0)),
        ((12.0, 19.0), (12.0, 21.2)),
        ((2.8, 12.0), (5.0, 12.0)),
        ((19.0, 12.0), (21.2, 12.0)),
        ((5.3, 5.3), (6.9, 6.9)),
        ((17.1, 17.1), (18.7, 18.7)),
        ((5.3, 18.7), (6.9, 17.1)),
        ((17.1, 6.9), (18.7, 5.3)),
    ]
    for a, b in rays:
        _line(draw, scale, [a, b], fill=scheme.accent, width=max(1, width - 1))


def _draw_moon(draw, scale, scheme: Scheme, width: int) -> None:
    _arc(
        draw,
        scale,
        (4.6, 3.0, 18.6, 21.0),
        start=65,
        end=298,
        fill=scheme.outline,
        width=width,
    )
    _arc(
        draw,
        scale,
        (8.8, 4.5, 21.0, 19.0),
        start=115,
        end=245,
        fill=scheme.outline,
        width=width,
    )
    for x, y, size in ((17.4, 7.8, 1.6), (20.0, 10.0, 1.2)):
        _line(
            draw,
            scale,
            [(x - size, y), (x + size, y)],
            fill=scheme.accent,
            width=max(1, width - 1),
        )
        _line(
            draw,
            scale,
            [(x, y - size), (x, y + size)],
            fill=scheme.accent,
            width=max(1, width - 1),
        )


def _draw_chip_zero(draw, scale, scheme: Scheme, width: int) -> None:
    _rect(
        draw,
        scale,
        (5.0, 5.0, 19.0, 19.0),
        radius=2.2,
        outline=scheme.outline,
        width=width,
    )
    for pos in (8.0, 12.0, 16.0):
        _line(
            draw,
            scale,
            [(pos, 2.2), (pos, 5.0)],
            fill=scheme.outline,
            width=max(1, width - 1),
        )
        _line(
            draw,
            scale,
            [(pos, 19.0), (pos, 21.8)],
            fill=scheme.outline,
            width=max(1, width - 1),
        )
        _line(
            draw,
            scale,
            [(2.2, pos), (5.0, pos)],
            fill=scheme.outline,
            width=max(1, width - 1),
        )
        _line(
            draw,
            scale,
            [(19.0, pos), (21.8, pos)],
            fill=scheme.outline,
            width=max(1, width - 1),
        )
    for x, y in ((8.2, 8.2), (12.4, 8.2), (8.2, 12.8), (12.4, 12.8)):
        _ellipse(
            draw,
            scale,
            (x, y, x + 2.6, y + 3.2),
            outline=scheme.accent,
            width=max(1, width - 1),
        )


def _draw_delete_user(draw, scale, scheme: Scheme, width: int) -> None:
    _ellipse(draw, scale, (7.0, 4.0, 13.8, 10.8), outline=scheme.outline, width=width)
    _line(
        draw,
        scale,
        [(5.2, 19.2), (7.6, 15.0), (13.4, 15.0), (15.8, 19.2)],
        fill=scheme.outline,
        width=width,
    )
    _rect(
        draw,
        scale,
        (13.8, 12.8, 20.0, 19.4),
        radius=1.0,
        outline=scheme.error,
        width=max(1, width - 1),
    )
    _line(
        draw,
        scale,
        [(15.2, 12.2), (18.6, 12.2)],
        fill=scheme.error,
        width=max(1, width - 1),
    )
    _line(
        draw,
        scale,
        [(16.0, 14.2), (16.0, 17.2)],
        fill=scheme.error,
        width=max(1, width - 1),
    )
    _line(
        draw,
        scale,
        [(18.0, 14.2), (18.0, 17.2)],
        fill=scheme.error,
        width=max(1, width - 1),
    )


# Compound assets ------------------------------------------------------------


def _draw_checkbox(checked: bool, disabled: bool, *, theme: str) -> Image.Image:
    image = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if theme == "dark":
        outline = "#7C8AA3" if not disabled else "#55657A"
        fill = "#111827" if not disabled else "#1C2638"
        accent = "#4EA3FF" if not disabled else "#2E3C55"
        check = "#FFFFFF" if not disabled else "#70809A"
    else:
        outline = "#7F8EA4" if not disabled else "#A8B4C6"
        fill = "#F8FAFC" if not disabled else "#E5EBF3"
        accent = "#1D8FFF" if not disabled else "#D4DCE8"
        check = "#FFFFFF" if not disabled else "#A8B4C6"
    draw.rounded_rectangle(
        (1, 1, 16, 16),
        radius=4,
        outline=outline,
        width=2,
        fill=accent if checked else fill,
    )
    if checked:
        draw.line([(4, 9), (7, 12), (13, 6)], fill=check, width=2, joint="curve")
    return image


def _draw_icon(name: str, size: int, scheme: Scheme) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = size / BASE
    width = max(2, round(2.2 * scale))

    draw_map = {
        "settings": _draw_settings,
        "sun": _draw_sun,
        "moon": _draw_moon,
        "chip": _draw_tag,
        "nfc": _draw_nfc,
        "write": _draw_write,
        "erase": _draw_erase,
        "diagnostic": _draw_diagnostic,
        "folder": _draw_folder,
        "report": _draw_report,
        "backup": _draw_backup,
        "plus": _draw_plus,
        "copy": _draw_copy,
        "cancel": _draw_cancel,
        "chevron_right": _draw_chevron,
        "check": _draw_check,
        "warning": _draw_warning,
        "error": _draw_error,
        "info": _draw_info,
        "skip": _draw_skip,
        "ready": _draw_ready,
        "delete_user_data": _draw_delete_user,
        "zero_memory": _draw_chip_zero,
    }
    handler = draw_map.get(name)
    if handler is None:
        raise ValueError(f"Unknown icon: {name}")
    handler(draw, scale, scheme, width)
    return image


def _load_app_icon_master() -> Image.Image:
    if not APP_ICON_SOURCE.is_file():
        raise FileNotFoundError(
            f"Application icon source is missing: {APP_ICON_SOURCE}"
        )
    with Image.open(APP_ICON_SOURCE) as source_file:
        source = source_file.convert("RGBA")

    alpha = source.getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= 5 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError("Application icon source has no visible pixels")

    cropped = source.crop(bounds)
    side = max(cropped.size)
    margin = max(1, round(side * 0.06))
    canvas = Image.new(
        "RGBA",
        (side + 2 * margin, side + 2 * margin),
        (0, 0, 0, 0),
    )
    canvas.alpha_composite(
        cropped,
        (
            (canvas.width - cropped.width) // 2,
            (canvas.height - cropped.height) // 2,
        ),
    )
    return canvas


def _draw_app_icon(size: int) -> Image.Image:
    master = _load_app_icon_master()
    return master.resize((size, size), Image.Resampling.LANCZOS)


# Main entry point -----------------------------------------------------------


def main() -> int:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    names = (
        "settings",
        "sun",
        "moon",
        "chip",
        "nfc",
        "write",
        "erase",
        "diagnostic",
        "folder",
        "report",
        "backup",
        "plus",
        "copy",
        "cancel",
        "chevron_right",
        "check",
        "warning",
        "error",
        "info",
        "skip",
        "ready",
    )

    schemes = {
        "light": Scheme(
            outline="#253247",
            accent="#1D8FFF",
            accent_soft="#7FBFFF",
            ok="#2EA043",
            warning="#F59E0B",
            error="#EF4444",
            info="#1D8FFF",
        ),
        "dark": Scheme(
            outline="#E7EEF8",
            accent="#4EA3FF",
            accent_soft="#86C0FF",
            ok="#86EFAC",
            warning="#FCD34D",
            error="#FDA4AF",
            info="#93C5FD",
        ),
        "inverse": Scheme(
            outline="#FFFFFF",
            accent="#4EA3FF",
            accent_soft="#86C0FF",
            ok="#86EFAC",
            warning="#FCD34D",
            error="#F87171",
            info="#93C5FD",
        ),
        "muted_light": Scheme(
            outline="#5B667A",
            accent="#6E9AD7",
            accent_soft="#8CB4E4",
            ok="#4D8F5D",
            warning="#B9811E",
            error="#CA6B6B",
            info="#6E9AD7",
        ),
        "muted_dark": Scheme(
            outline="#A7B1C2",
            accent="#7FB6FF",
            accent_soft="#A4CCFF",
            ok="#8FD3A7",
            warning="#E2C06B",
            error="#F0A5A5",
            info="#A4CCFF",
        ),
    }

    for variant in ("light", "dark", "inverse"):
        directory = OUTPUT / variant
        directory.mkdir(parents=True, exist_ok=True)
        for size in (20, 32):
            for name in names:
                _draw_icon(name, size, schemes[variant]).save(
                    directory / f"{name}_{size}.png"
                )

    for variant in ("muted_light", "muted_dark"):
        directory = OUTPUT / variant
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            _draw_icon(name, 20, schemes[variant]).save(directory / f"{name}_20.png")

    status_assets = {
        "ok_light": (
            "check",
            Scheme(outline="#5B667A", accent="#5B667A", ok="#166534"),
        ),
        "ok_dark": (
            "check",
            Scheme(outline="#CBD5E1", accent="#CBD5E1", ok="#86EFAC"),
        ),
        "warning_light": (
            "warning",
            Scheme(outline="#92400E", accent="#92400E", warning="#92400E"),
        ),
        "warning_dark": (
            "warning",
            Scheme(outline="#FCD34D", accent="#FCD34D", warning="#FCD34D"),
        ),
        "error_light": (
            "error",
            Scheme(outline="#B91C1C", accent="#B91C1C", error="#B91C1C"),
        ),
        "error_dark": (
            "error",
            Scheme(outline="#FDA4AF", accent="#FDA4AF", error="#FDA4AF"),
        ),
        "info_light": (
            "info",
            Scheme(outline="#1D4ED8", accent="#1D4ED8", info="#1D4ED8"),
        ),
        "info_dark": (
            "info",
            Scheme(outline="#93C5FD", accent="#93C5FD", info="#93C5FD"),
        ),
        "skip_light": (
            "skip",
            Scheme(outline="#64748B", accent="#64748B"),
        ),
        "skip_dark": (
            "skip",
            Scheme(outline="#CBD5E1", accent="#CBD5E1"),
        ),
    }
    for variant, (name, scheme) in status_assets.items():
        directory = OUTPUT / variant
        directory.mkdir(parents=True, exist_ok=True)
        _draw_icon(name, 18, scheme).save(directory / f"{name}_18.png")

    for theme in ("light", "dark"):
        directory = OUTPUT / theme
        for checked in (False, True):
            for disabled in (False, True):
                state = "on" if checked else "off"
                if disabled:
                    state += "_disabled"
                _draw_checkbox(checked, disabled, theme=theme).save(
                    directory / f"checkbox_{state}_18.png"
                )

    asset_root = OUTPUT.parent
    master = _load_app_icon_master()
    master.save(asset_root / "app_icon_master_preview.png")
    app_sizes = (32, 64, 128, 256)
    images = []
    for size in app_sizes:
        image = _draw_app_icon(size)
        image.save(asset_root / f"app_icon_{size}.png")
        images.append(image)

    images[-1].save(
        asset_root / "app_icon.ico",
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    print(
        f"Generated {sum(1 for _ in OUTPUT.rglob('*.png'))} themed icons "
        f"and {len(app_sizes)} application PNG icons"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
