from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections.abc import Callable

from ..theme import ThemeManager
from ..widgets import AutoHideScrollbar


class ThemedDialogs:
    """Display modal dialogs that follow the application's active theme."""

    def __init__(
        self,
        parent: tk.Tk,
        theme: ThemeManager,
        translate: Callable[..., str],
    ) -> None:
        self.parent = parent
        self.theme = theme
        self.t = translate

    def info(self, title: str, message: str) -> None:
        self._show(title, message, kind="info")

    def warning(self, title: str, message: str) -> None:
        self._show(title, message, kind="warning")

    def error(self, title: str, message: str) -> None:
        self._show(title, message, kind="error")

    def text_info(self, title: str, summary: str, content: str) -> None:
        """Show copyable, scrollable text in a themed modal window."""

        window = tk.Toplevel(self.parent)
        window.title(title)
        window.transient(self.parent)
        window.minsize(560, 360)
        window.geometry("720x520")
        window.configure(background=self.theme.palette.window)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        card = ttk.Frame(window, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True, padx=18, pady=18)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        ttk.Label(
            card,
            text=title,
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 13),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            text=summary,
            style="SurfaceMuted.TLabel",
            justify="left",
            wraplength=640,
        ).grid(row=1, column=0, sticky="ew", pady=(6, 12))

        text_frame = ttk.Frame(card, style="Surface.TFrame")
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        text_widget = tk.Text(
            text_frame,
            wrap="none",
            font=("Consolas", 10),
            padx=10,
            pady=10,
        )
        self.theme.configure_log_text(text_widget)
        text_widget.grid(row=0, column=0, sticky="nsew")
        y_scroll = AutoHideScrollbar(
            text_frame, orient="vertical", command=text_widget.yview
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = AutoHideScrollbar(
            text_frame, orient="horizontal", command=text_widget.xview
        )
        x_scroll.grid(row=1, column=0, sticky="ew")
        text_widget.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        text_widget.insert("1.0", content)
        text_widget.configure(state="disabled")

        buttons = ttk.Frame(card, style="Surface.TFrame")
        buttons.grid(row=3, column=0, sticky="e", pady=(12, 0))

        def copy_content() -> None:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(content)

        ttk.Button(
            buttons,
            text=self.t("dialog.copy"),
            command=copy_content,
        ).grid(row=0, column=0, padx=(0, 8))
        close_button = ttk.Button(
            buttons,
            text=self.t("dialog.close"),
            style="Type2Accent.TButton",
            command=window.destroy,
        )
        close_button.grid(row=0, column=1)
        close_button.focus_set()
        window.bind("<Escape>", lambda _event: window.destroy())

        window.update_idletasks()
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        width = window.winfo_width()
        height = window.winfo_height()
        x = max(0, parent_x + (parent_width - width) // 2)
        y = max(0, parent_y + (parent_height - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.grab_set()
        window.wait_window()

    def confirm(
        self,
        title: str,
        message: str,
        *,
        accent: str = "cuid",
        destructive: bool = False,
    ) -> bool:
        return bool(
            self._show(
                title,
                message,
                kind="warning",
                confirm=True,
                accent=accent,
                destructive=destructive,
            )
        )

    def _show(
        self,
        title: str,
        message: str,
        *,
        kind: str,
        confirm: bool = False,
        accent: str = "cuid",
        destructive: bool = False,
    ) -> bool | None:
        window = tk.Toplevel(self.parent)
        window.title(title)
        window.transient(self.parent)
        window.resizable(False, False)
        window.configure(background=self.theme.palette.window)

        result: dict[str, bool | None] = {"value": None}

        def close(value: bool | None = None) -> None:
            result["value"] = value
            try:
                window.grab_release()
            except tk.TclError:
                pass
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", lambda: close(False if confirm else None))

        card = ttk.Frame(window, style="Card.TFrame", padding=22)
        card.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        card.columnconfigure(1, weight=1)

        icon_state = {
            "info": "info",
            "warning": "warning",
            "error": "error",
        }.get(kind, "info")
        ttk.Label(
            card,
            image=self.theme.status_icon(icon_state),
            style="Surface.TLabel",
        ).grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 14))
        ttk.Label(
            card,
            text=title,
            style="Surface.TLabel",
            font=("Segoe UI Semibold", 13),
        ).grid(row=0, column=1, sticky="w")
        message_label = ttk.Label(
            card,
            text=message,
            style="SurfaceMuted.TLabel",
            justify="left",
            wraplength=520,
        )
        message_label.grid(row=1, column=1, sticky="ew", pady=(7, 18))

        buttons = ttk.Frame(card, style="Surface.TFrame")
        buttons.grid(row=2, column=0, columnspan=2, sticky="e")

        if confirm:
            no_button = ttk.Button(
                buttons,
                text=self.t("dialog.no"),
                command=lambda: close(False),
            )
            no_button.grid(row=0, column=0, padx=(0, 8))
            if destructive:
                confirm_style = "Danger.TButton"
            elif accent == "type2":
                confirm_style = "Type2Accent.TButton"
            else:
                confirm_style = "CuidAccent.TButton"
            yes_button = ttk.Button(
                buttons,
                text=self.t("dialog.yes"),
                style=confirm_style,
                command=lambda: close(True),
            )
            yes_button.grid(row=0, column=1)
            no_button.focus_set()
            window.bind("<Escape>", lambda _event: close(False))
        else:
            ok_button = ttk.Button(
                buttons,
                text=self.t("dialog.ok"),
                style="Type2Accent.TButton" if kind == "info" else "TButton",
                command=lambda: close(None),
            )
            ok_button.grid(row=0, column=0)
            ok_button.focus_set()
            window.bind("<Escape>", lambda _event: close(None))
            window.bind("<Return>", lambda _event: close(None))

        window.update_idletasks()
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        x = max(0, parent_x + (parent_width - width) // 2)
        y = max(0, parent_y + (parent_height - height) // 2)
        window.geometry(f"+{x}+{y}")
        window.grab_set()
        window.wait_window()
        return result["value"]
