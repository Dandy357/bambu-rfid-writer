from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import VERTICAL
from tkinter import ttk


class AutoHideScrollbar(ttk.Scrollbar):
    """A grid-managed scrollbar that is visible only when scrolling is possible."""

    def __init__(self, parent: tk.Misc, **kwargs: object) -> None:
        super().__init__(parent, **kwargs)
        self._layout_initialized = False
        self._visible = False

    def grid(self, *args: object, **kwargs: object) -> None:
        super().grid(*args, **kwargs)
        self._layout_initialized = True
        self._visible = False
        self.grid_remove()

    def set(self, first: str, last: str) -> None:
        try:
            start = float(first)
            end = float(last)
        except (TypeError, ValueError):
            super().set(first, last)
            return

        scrolling_needed = start > 1e-9 or end < 1.0 - 1e-9
        if self._layout_initialized:
            if scrolling_needed and not self._visible:
                self._visible = True
                ttk.Scrollbar.grid(self)
            elif not scrolling_needed and self._visible:
                self._visible = False
                self.grid_remove()
        super().set(first, last)


class _MouseWheelRouter:
    """Route wheel events to the outer scroll frame under the pointer."""

    _ATTRIBUTE = "_bambu_mouse_wheel_router"

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._scrollers: weakref.WeakSet[VerticalScrolledFrame] = weakref.WeakSet()
        root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        root.bind_all("<Button-4>", self._on_mousewheel, add="+")
        root.bind_all("<Button-5>", self._on_mousewheel, add="+")

    @classmethod
    def for_widget(cls, widget: tk.Misc) -> "_MouseWheelRouter":
        root = widget.winfo_toplevel()
        existing = getattr(root, cls._ATTRIBUTE, None)
        if isinstance(existing, cls):
            return existing
        router = cls(root)
        setattr(root, cls._ATTRIBUTE, router)
        return router

    def register(self, scroller: "VerticalScrolledFrame") -> None:
        self._scrollers.add(scroller)

    @staticmethod
    def _contains(container: tk.Misc, widget: tk.Misc | None) -> bool:
        current = widget
        while current is not None:
            if current == container:
                return True
            parent_name = current.winfo_parent()
            if not parent_name:
                return False
            try:
                current = current._nametowidget(parent_name)
            except KeyError:
                return False
        return False

    @staticmethod
    def _inner_scroll_widget(
        widget: tk.Misc | None, boundary: tk.Misc
    ) -> tk.Misc | None:
        current = widget
        while current is not None and current != boundary:
            if isinstance(current, (tk.Text, tk.Listbox, ttk.Treeview)):
                return current
            if isinstance(current, tk.Canvas) and current != boundary:
                return current
            parent_name = current.winfo_parent()
            if not parent_name:
                break
            try:
                current = current._nametowidget(parent_name)
            except KeyError:
                break
        return None

    @staticmethod
    def _can_scroll(widget: tk.Misc, units: int) -> bool:
        try:
            start, end = widget.yview()
        except (tk.TclError, AttributeError, TypeError, ValueError):
            return False
        if end - start >= 0.999999:
            return False
        return (units < 0 and start > 0.0) or (units > 0 and end < 1.0)

    @staticmethod
    def _wheel_units(event: tk.Event) -> int:
        number = getattr(event, "num", None)
        if number == 4:
            return -1
        if number == 5:
            return 1
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return 0
        if abs(delta) >= 120:
            return max(-8, min(8, int(-delta / 120)))
        return -1 if delta > 0 else 1

    def _target_scroller(self, widget: tk.Misc | None) -> "VerticalScrolledFrame | None":
        matches: list[VerticalScrolledFrame] = []
        for scroller in list(self._scrollers):
            try:
                if scroller.winfo_exists() and self._contains(scroller, widget):
                    matches.append(scroller)
            except tk.TclError:
                continue
        if not matches:
            return None
        return max(matches, key=lambda item: len(str(item).split(".")))

    def _on_mousewheel(self, event: tk.Event) -> str | None:
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except tk.TclError:
            return None
        scroller = self._target_scroller(widget)
        if scroller is None:
            return None
        units = self._wheel_units(event)
        inner = self._inner_scroll_widget(widget, scroller.canvas)
        if inner is not None and self._can_scroll(inner, units):
            return None
        if units == 0:
            return None
        start, end = scroller.canvas.yview()
        if (units < 0 and start <= 0.0) or (units > 0 and end >= 1.0):
            return None
        scroller.canvas.yview_scroll(units, "units")
        return "break"


class VerticalScrolledFrame(ttk.Frame):
    """A vertically scrollable ttk frame with cross-platform wheel routing."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        padding: int = 0,
        background: str | None = None,
        fill_height: bool = False,
    ) -> None:
        super().__init__(parent)
        self.fill_height = bool(fill_height)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        canvas_background = background or ttk.Style(parent).lookup(
            "TFrame", "background"
        )
        if not canvas_background:
            raise ValueError("A scrollable frame requires a resolved background color")
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            background=canvas_background,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = AutoHideScrollbar(
            self, orient=VERTICAL, command=self.canvas.yview
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.content = ttk.Frame(self.canvas, padding=padding)
        self._window = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw"
        )
        self._scrollregion_after_id: str | None = None
        self._width_after_id: str | None = None
        self._pending_width = 1
        self._pending_height = 1
        # ``winfo_reqheight()`` cannot be used as the minimum for a fill-height
        # canvas window. Widgets such as ttk.Panedwindow may retain a previously
        # allocated height as their new request, which creates a one-way growth
        # loop and an empty scrollable tail after the viewport shrinks.
        self._content_min_height = 1
        self.content.bind("<Configure>", self._schedule_content_layout)
        self.canvas.bind("<Configure>", self._schedule_width)
        self._wheel_router = _MouseWheelRouter.for_widget(self)
        self._wheel_router.register(self)

    def _schedule_content_layout(self, _event: object | None = None) -> None:
        self._schedule_scrollregion()
        if self.fill_height:
            self._schedule_size(
                self.canvas.winfo_width(),
                self.canvas.winfo_height(),
            )

    def _schedule_scrollregion(self, _event: object | None = None) -> None:
        if self._scrollregion_after_id is not None:
            try:
                self.after_cancel(self._scrollregion_after_id)
            except tk.TclError:
                pass
        self._scrollregion_after_id = self.after(30, self._sync_scrollregion)

    def _sync_scrollregion(self) -> None:
        self._scrollregion_after_id = None
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            return

    def _schedule_width(self, event: tk.Event) -> None:
        self._schedule_size(event.width, event.height)

    def _schedule_size(self, width: int, height: int) -> None:
        self._pending_width = max(1, int(width))
        self._pending_height = max(1, int(height))
        if self._width_after_id is not None:
            try:
                self.after_cancel(self._width_after_id)
            except tk.TclError:
                pass
        self._width_after_id = self.after(20, self._sync_width)

    def set_content_min_height(self, height: int) -> None:
        """Set the logical content height used by a fill-height scroller.

        The value must describe the controls that actually need space, not the
        frame's current allocated height. This lets the scroll region shrink
        again after a window or divider was previously enlarged.
        """

        value = max(1, int(height))
        if value != self._content_min_height:
            self._content_min_height = value
        self.refresh_layout()

    @property
    def content_min_height(self) -> int:
        return self._content_min_height

    def refresh_layout(self) -> None:
        """Recompute the canvas window size and scroll region after child layout changes."""

        self._schedule_size(self.canvas.winfo_width(), self.canvas.winfo_height())
        self._schedule_scrollregion()

    def _sync_width(self) -> None:
        self._width_after_id = None
        try:
            current = int(float(self.canvas.itemcget(self._window, "width") or 0))
            configuration: dict[str, int] = {}
            if current != self._pending_width:
                configuration["width"] = self._pending_width
            if self.fill_height:
                target_height = max(self._pending_height, self._content_min_height)
                current_height = int(
                    float(self.canvas.itemcget(self._window, "height") or 0)
                )
                if current_height != target_height:
                    configuration["height"] = target_height
            if configuration:
                self.canvas.itemconfigure(self._window, **configuration)
                # Canvas window item changes do not consistently emit a child
                # <Configure> event on every Tk build. Refresh explicitly so a
                # reduced height immediately removes the obsolete empty region.
                self._schedule_scrollregion()
        except (tk.TclError, TypeError, ValueError):
            return

    def destroy(self) -> None:
        for after_id in (self._scrollregion_after_id, self._width_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        super().destroy()
