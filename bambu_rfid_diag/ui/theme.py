from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk


LIGHT = "light"
DARK = "dark"
THEME_NAMES = (LIGHT, DARK)


@dataclass(frozen=True)
class ThemePalette:
    name: str
    window: str
    surface: str
    surface_alt: str
    field: str
    field_hover: str
    field_disabled: str
    text: str
    text_muted: str
    text_disabled: str
    border: str
    border_strong: str
    selection: str
    selection_text: str
    cuid: str
    cuid_hover: str
    type2: str
    type2_hover: str
    danger: str
    danger_hover: str
    warning_surface: str
    warning_border: str
    success_surface: str
    success_border: str
    track: str
    log_background: str
    log_text: str
    log_muted: str
    ok: str
    warning: str
    error: str
    info: str
    skipped: str


PALETTES = {
    LIGHT: ThemePalette(
        name=LIGHT,
        window="#F4F7FB",
        surface="#FFFFFF",
        surface_alt="#EEF3F8",
        field="#F8FAFC",
        field_hover="#FFFFFF",
        field_disabled="#E8EDF4",
        text="#172033",
        text_muted="#5B667A",
        text_disabled="#94A0B2",
        border="#C7D2E0",
        border_strong="#9AA9BC",
        selection="#DCE7FF",
        selection_text="#172033",
        cuid="#4338CA",
        cuid_hover="#3730A3",
        type2="#0F766E",
        type2_hover="#0B5F59",
        danger="#B42318",
        danger_hover="#8F1C13",
        warning_surface="#FFF7E6",
        warning_border="#F2C66D",
        success_surface="#EAF8F0",
        success_border="#87CDA5",
        track="#D7E0EB",
        log_background="#F7F9FC",
        log_text="#172033",
        log_muted="#6B778A",
        ok="#166534",
        warning="#92400E",
        error="#B91C1C",
        info="#1D4ED8",
        skipped="#64748B",
    ),
    DARK: ThemePalette(
        name=DARK,
        window="#0B1220",
        surface="#111827",
        surface_alt="#172033",
        field="#141E2E",
        field_hover="#19263A",
        field_disabled="#202C40",
        text="#E7EEF8",
        text_muted="#A7B1C2",
        text_disabled="#66748A",
        border="#344258",
        border_strong="#53637B",
        selection="#263B68",
        selection_text="#F8FBFF",
        cuid="#4F46E5",
        cuid_hover="#4338CA",
        type2="#0F766E",
        type2_hover="#0B5F59",
        danger="#BE123C",
        danger_hover="#9F1239",
        warning_surface="#352A16",
        warning_border="#8D6B26",
        success_surface="#173326",
        success_border="#387C59",
        track="#29364A",
        log_background="#080D17",
        log_text="#DCE6F4",
        log_muted="#8793A6",
        ok="#86EFAC",
        warning="#FCD34D",
        error="#FDA4AF",
        info="#93C5FD",
        skipped="#CBD5E1",
    ),
}


class IconRepository:
    """Load and retain Tk image objects used by themed widgets."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.directory = Path(__file__).resolve().parents[1] / "assets" / "icons"
        self._cache: dict[tuple[str, str, int], tk.PhotoImage] = {}

    def get(self, name: str, variant: str, size: int = 20) -> tk.PhotoImage:
        key = (name, variant, size)
        image = self._cache.get(key)
        if image is not None:
            return image
        path = self.directory / variant / f"{name}_{size}.png"
        if not path.is_file():
            raise FileNotFoundError(f"Missing icon asset: {path}")
        image = tk.PhotoImage(master=self.root, file=str(path))
        self._cache[key] = image
        return image


class ThemeManager:
    """Apply the complete visual system and provide themed icon assets."""

    def __init__(self, root: tk.Tk, name: str = LIGHT) -> None:
        self.root = root
        self.name = name if name in THEME_NAMES else LIGHT
        self.icons = IconRepository(root)
        self.style = ttk.Style(root)
        self._checkbox_elements: set[str] = set()

    @property
    def palette(self) -> ThemePalette:
        return PALETTES[self.name]

    @property
    def icon_variant(self) -> str:
        return "dark" if self.name == DARK else "light"

    @property
    def muted_icon_variant(self) -> str:
        return "muted_dark" if self.name == DARK else "muted_light"

    def icon(self, name: str, *, size: int = 20, inverse: bool = False) -> tk.PhotoImage:
        variant = "inverse" if inverse else self.icon_variant
        return self.icons.get(name, variant, size)

    def muted_icon(self, name: str, *, size: int = 20) -> tk.PhotoImage:
        return self.icons.get(name, self.muted_icon_variant, size)

    def status_icon(self, state: str) -> tk.PhotoImage:
        normalized = state.lower()
        if normalized == "ok":
            name, prefix = "check", "ok"
        elif normalized in {"warning", "indeterminate"}:
            name, prefix = "warning", "warning"
        elif normalized == "error":
            name, prefix = "error", "error"
        elif normalized == "info":
            name, prefix = "info", "info"
        else:
            name, prefix = "skip", "skip"
        variant = f"{prefix}_{self.name}"
        return self.icons.get(name, variant, 18)

    def apply(self) -> None:
        palette = self.palette
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.root.configure(background=palette.window)
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.option_add("*TCombobox*Listbox.background", palette.field)
        self.root.option_add("*TCombobox*Listbox.foreground", palette.text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", palette.selection)
        self.root.option_add("*TCombobox*Listbox.selectForeground", palette.selection_text)
        self.root.option_add("*Text.selectBackground", palette.selection)
        self.root.option_add("*Text.selectForeground", palette.selection_text)

        self.style.configure(".", background=palette.window, foreground=palette.text)
        self.style.configure("TFrame", background=palette.window)
        self.style.configure("Surface.TFrame", background=palette.surface)
        self.style.configure("AltSurface.TFrame", background=palette.surface_alt)
        self.style.configure(
            "Card.TFrame",
            background=palette.surface,
            bordercolor=palette.border,
            borderwidth=1,
            relief="solid",
        )
        self.style.configure(
            "Card.TLabelframe",
            background=palette.surface,
            bordercolor=palette.border,
            borderwidth=1,
            relief="solid",
        )
        self.style.configure(
            "Card.TLabelframe.Label",
            background=palette.surface,
            foreground=palette.text,
            font=("Segoe UI", 10, "bold"),
        )
        self.style.configure("TLabel", background=palette.window, foreground=palette.text)
        self.style.configure("Surface.TLabel", background=palette.surface, foreground=palette.text)
        self.style.configure("Muted.TLabel", foreground=palette.text_muted)
        self.style.configure(
            "SurfaceMuted.TLabel",
            background=palette.surface,
            foreground=palette.text_muted,
        )
        self.style.configure(
            "Title.TLabel",
            font=("Segoe UI Semibold", 20),
            foreground=palette.text,
        )
        self.style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 10),
            foreground=palette.text_muted,
        )
        self.style.configure(
            "Result.TLabel",
            font=("Segoe UI Semibold", 11),
            foreground=palette.text,
        )
        self.style.configure(
            "Section.TLabel",
            font=("Segoe UI Semibold", 11),
            foreground=palette.text,
        )
        self.style.configure("Safe.TLabel", font=("Segoe UI Semibold", 10), foreground=palette.ok)
        self.style.configure(
            "Warning.TLabel",
            font=("Segoe UI Semibold", 10),
            foreground=palette.warning,
        )
        self.style.configure("DangerText.TLabel", foreground=palette.error)

        self._configure_buttons()
        self._configure_fields()
        self._configure_checkbuttons()
        self._configure_notebook()
        self._configure_treeview()
        self._configure_scrollbars()

    def _configure_buttons(self) -> None:
        p = self.palette
        self.style.configure(
            "TButton",
            background=p.surface_alt,
            foreground=p.text,
            bordercolor=p.border,
            lightcolor=p.surface_alt,
            darkcolor=p.surface_alt,
            padding=(12, 7),
            relief="flat",
            font=("Segoe UI Semibold", 9),
        )
        self.style.map(
            "TButton",
            background=[
                ("disabled", p.field_disabled),
                ("pressed", p.border),
                ("active", p.field_hover),
            ],
            foreground=[("disabled", p.text_disabled)],
            bordercolor=[("focus", p.border_strong), ("active", p.border_strong)],
        )
        for style_name, color, hover in (
            ("CuidAccent.TButton", p.cuid, p.cuid_hover),
            ("Type2Accent.TButton", p.type2, p.type2_hover),
            ("Danger.TButton", p.danger, p.danger_hover),
        ):
            self.style.configure(
                style_name,
                background=color,
                foreground="#FFFFFF",
                bordercolor=color,
                lightcolor=color,
                darkcolor=color,
                padding=(18, 11),
                font=("Segoe UI Semibold", 11),
                relief="flat",
            )
            self.style.map(
                style_name,
                background=[("disabled", p.field_disabled), ("pressed", hover), ("active", hover)],
                foreground=[("disabled", p.text_disabled)],
                bordercolor=[("focus", p.selection), ("active", hover)],
            )
        self.style.configure(
            "WarningOutline.TButton",
            background=p.surface,
            foreground=p.warning,
            bordercolor=p.warning,
            padding=(13, 8),
            font=("Segoe UI Semibold", 9),
            relief="flat",
        )
        self.style.map(
            "WarningOutline.TButton",
            background=[
                ("active", p.warning_surface),
                ("pressed", p.warning_surface),
                ("disabled", p.field_disabled),
            ],
            foreground=[("disabled", p.text_disabled)],
        )
        self.style.configure(
            "Icon.TButton",
            background=p.surface,
            foreground=p.text,
            bordercolor=p.border,
            padding=(9, 7),
            relief="flat",
        )
        self.style.map(
            "Icon.TButton",
            background=[
                ("active", p.surface_alt),
                ("pressed", p.selection),
                ("disabled", p.field_disabled),
            ],
        )
        self.style.configure(
            "ModeIdle.TButton",
            background=p.surface,
            foreground=p.text,
            bordercolor=p.border,
            padding=(16, 9),
            font=("Segoe UI Semibold", 10),
            relief="flat",
        )
        self.style.map(
            "ModeIdle.TButton",
            background=[("active", p.surface_alt), ("pressed", p.surface_alt)],
        )
        for style_name, color, hover in (
            ("ModeCuid.TButton", p.cuid, p.cuid_hover),
            ("ModeType2.TButton", p.type2, p.type2_hover),
        ):
            self.style.configure(
                style_name,
                background=color,
                foreground="#FFFFFF",
                bordercolor=color,
                padding=(16, 9),
                font=("Segoe UI Semibold", 10),
                relief="flat",
            )
            self.style.map(
                style_name,
                background=[("active", hover), ("pressed", hover)],
            )

        self.style.configure(
            "ModeSettingsIdle.TButton",
            background=p.surface,
            foreground=p.text,
            bordercolor=p.border,
            padding=(8, 6),
            relief="flat",
        )
        self.style.map(
            "ModeSettingsIdle.TButton",
            background=[("active", p.surface_alt), ("pressed", p.surface_alt)],
        )
        self.style.configure(
            "ModeSettingsSelected.TButton",
            background=p.border_strong,
            foreground="#FFFFFF",
            bordercolor=p.border_strong,
            padding=(8, 6),
            relief="flat",
        )
        self.style.map(
            "ModeSettingsSelected.TButton",
            background=[("active", p.text_muted), ("pressed", p.text_muted)],
        )

    def _configure_fields(self) -> None:
        p = self.palette
        self.style.configure(
            "TEntry",
            fieldbackground=p.field,
            foreground=p.text,
            insertcolor=p.text,
            bordercolor=p.border,
            lightcolor=p.field,
            darkcolor=p.field,
            padding=(9, 7),
            relief="flat",
        )
        self.style.map(
            "TEntry",
            fieldbackground=[
                ("disabled", p.field_disabled),
                ("readonly", p.surface_alt),
                ("focus", p.field_hover),
            ],
            foreground=[("disabled", p.text_disabled), ("readonly", p.text_muted)],
            bordercolor=[("focus", p.cuid), ("invalid", p.error), ("hover", p.border_strong)],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=p.field,
            background=p.field,
            foreground=p.text,
            arrowcolor=p.text_muted,
            bordercolor=p.border,
            lightcolor=p.field,
            darkcolor=p.field,
            padding=(8, 6),
            relief="flat",
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", p.field),
                ("disabled", p.field_disabled),
                ("focus", p.field_hover),
            ],
            foreground=[("disabled", p.text_disabled), ("readonly", p.text)],
            background=[("readonly", p.field), ("disabled", p.field_disabled)],
            arrowcolor=[("disabled", p.text_disabled), ("active", p.text)],
            bordercolor=[("focus", p.cuid), ("hover", p.border_strong)],
        )

    def _configure_checkbuttons(self) -> None:
        p = self.palette
        element_name = f"Modern.Checkbutton.indicator.{self.name}"
        if element_name not in self._checkbox_elements:
            off = self.icons.get("checkbox_off", self.name, 18)
            on = self.icons.get("checkbox_on", self.name, 18)
            off_disabled = self.icons.get("checkbox_off_disabled", self.name, 18)
            on_disabled = self.icons.get("checkbox_on_disabled", self.name, 18)
            try:
                self.style.element_create(
                    element_name,
                    "image",
                    off,
                    ("disabled selected", on_disabled),
                    ("disabled", off_disabled),
                    ("selected", on),
                    sticky="",
                )
            except tk.TclError:
                pass
            self._checkbox_elements.add(element_name)
        self.style.layout(
            "TCheckbutton",
            [
                (
                    "Checkbutton.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            (element_name, {"side": "left", "sticky": ""}),
                            (
                                "Checkbutton.focus",
                                {
                                    "side": "left",
                                    "sticky": "w",
                                    "children": [("Checkbutton.label", {"sticky": "nswe"})],
                                },
                            ),
                        ],
                    },
                )
            ],
        )
        self.style.configure("TCheckbutton", background=p.window, foreground=p.text, padding=(2, 3))
        self.style.map(
            "TCheckbutton",
            background=[("active", p.window)],
            foreground=[("disabled", p.text_disabled)],
        )
        self.style.configure(
            "Surface.TCheckbutton",
            background=p.surface,
            foreground=p.text,
            padding=(2, 3),
        )
        self.style.map(
            "Surface.TCheckbutton",
            background=[("active", p.surface)],
            foreground=[("disabled", p.text_disabled)],
        )

    def _configure_notebook(self) -> None:
        p = self.palette
        self.style.configure(
            "TNotebook",
            background=p.window,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        self.style.configure(
            "TNotebook.Tab",
            background=p.surface_alt,
            foreground=p.text_muted,
            bordercolor=p.border,
            padding=(16, 9),
            font=("Segoe UI Semibold", 9),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", p.surface), ("active", p.field_hover)],
            foreground=[("selected", p.text), ("active", p.text)],
            bordercolor=[("selected", p.border_strong)],
        )

    def _configure_treeview(self) -> None:
        p = self.palette
        self.style.configure(
            "Treeview",
            background=p.surface,
            fieldbackground=p.surface,
            foreground=p.text,
            bordercolor=p.border,
            rowheight=31,
            font=("Segoe UI", 9),
            relief="flat",
        )
        self.style.map(
            "Treeview",
            background=[("selected", p.selection)],
            foreground=[("selected", p.selection_text)],
        )
        self.style.configure(
            "Treeview.Heading",
            background=p.surface_alt,
            foreground=p.text,
            bordercolor=p.border,
            padding=(8, 7),
            font=("Segoe UI Semibold", 9),
            relief="flat",
        )
        self.style.map("Treeview.Heading", background=[("active", p.field_hover)])

    def _configure_scrollbars(self) -> None:
        p = self.palette
        self.style.configure(
            "TScrollbar",
            background=p.border,
            troughcolor=p.surface_alt,
            bordercolor=p.surface_alt,
            arrowcolor=p.text_muted,
            relief="flat",
        )
        self.style.map(
            "TScrollbar",
            background=[
                ("active", p.border_strong),
                ("pressed", p.text_muted),
            ],
        )

    def configure_diagnostic_tree(self, tree: ttk.Treeview) -> None:
        p = self.palette
        colors = {
            "ok": p.ok,
            "warning": p.warning,
            "error": p.error,
            "info": p.info,
            "skipped": p.skipped,
            "unsupported": p.skipped,
            "indeterminate": p.warning,
        }
        for tag, color in colors.items():
            tree.tag_configure(tag, foreground=color)

    def configure_canvas(self, canvas: tk.Canvas, *, surface: bool = False) -> None:
        canvas.configure(background=self.palette.surface if surface else self.palette.window)

    def configure_log_text(self, widget: tk.Text) -> None:
        p = self.palette
        widget.configure(
            background=p.log_background,
            foreground=p.log_text,
            insertbackground=p.log_text,
            selectbackground=p.selection,
            selectforeground=p.selection_text,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=p.border,
            highlightcolor=p.border_strong,
        )
        widget.tag_configure("pm3_ok", foreground=p.ok)
        widget.tag_configure("pm3_error", foreground=p.error)
        widget.tag_configure("pm3_warning", foreground=p.warning)
        widget.tag_configure("pm3_info", foreground=p.info)
        widget.tag_configure("pm3_muted", foreground=p.log_muted)
