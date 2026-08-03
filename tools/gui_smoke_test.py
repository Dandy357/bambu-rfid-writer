from __future__ import annotations

import json
import os
import sys
import tempfile
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bambu_rfid_diag.app import WriterApp
from bambu_rfid_diag.domain.operation_events import UiEvent
from bambu_rfid_diag.ui.constants import MODE_CUID, MODE_SETTINGS, MODE_TYPE2
from bambu_rfid_diag.ui.theme import DARK, LIGHT


def _assert_theme(app: WriterApp, expected: str) -> None:
    if app.appearance != expected:
        raise RuntimeError(f"Expected {expected} theme, got {app.appearance}")
    palette = app.theme.palette
    entry_background = app.theme.style.lookup("TEntry", "fieldbackground")
    if entry_background.lower() != palette.field.lower():
        raise RuntimeError("Entry fields did not receive the active theme background")
    tree_background = app.theme.style.lookup("Treeview", "fieldbackground")
    if tree_background.lower() != palette.surface.lower():
        raise RuntimeError("Treeview did not receive the active theme background")
    if not app.theme.style.layout("TCheckbutton"):
        raise RuntimeError("The custom checkbutton layout is missing")


def _create_library(base: Path) -> Path:
    library = base / "library"
    source = library / "PETG" / "PETG Basic" / "Black" / "A1B2C3D4"
    source.mkdir(parents=True)
    dump = bytearray(1024)
    dump[:5] = bytes.fromhex("A1B2C3D404")
    (source / "hf-mf-A1B2C3D4-dump.bin").write_bytes(dump)
    (source / "hf-mf-A1B2C3D4-key.bin").write_bytes(bytes(192))
    return library


def run_smoke_test(base: Path) -> None:
    library = _create_library(base)
    root = tk.Tk()
    app = WriterApp(root)
    root.update_idletasks()
    root.update()

    if app.locale != "en":
        raise RuntimeError("A clean installation did not start in English")
    if len(app.mode_views) != 2:
        raise RuntimeError("Both protocol screens were not created")
    if not hasattr(app, "settings_mode"):
        raise RuntimeError("The Settings page was not created")
    if not hasattr(root, "_bambu_rfid_app_icon"):
        raise RuntimeError("The application icon was not applied to the root window")
    if root.winfo_width() < 860 or root.winfo_height() < 640:
        raise RuntimeError("The main window did not honor its minimum size")
    _assert_theme(app, LIGHT)
    root.after(80, root.quit)
    root.mainloop()
    initial_cuid_scroller = app.mode_views[MODE_CUID]["write_scroller"]
    if initial_cuid_scroller.scrollbar.winfo_manager():
        raise RuntimeError("The CUID scrollbar stayed visible while the page fitted")
    if app.cuid_mode.winfo_manager() != "grid":
        raise RuntimeError("The active CUID page is not managed")
    if app.ntag_mode.winfo_manager() or app.settings_mode.winfo_manager():
        raise RuntimeError("Inactive primary pages still participate in resize layout")

    app.material_library_var.set(str(library))
    if not app._load_material_library(False):
        raise RuntimeError("The material library did not load")
    library_item_count = len(app.source_items)
    if library_item_count != 1:
        raise RuntimeError("The material library tree has an unexpected item count")

    root.geometry("860x640")
    root.update_idletasks()
    root.update()
    root.after(100, root.quit)
    root.mainloop()
    cuid_scroller = app.mode_views[MODE_CUID]["write_scroller"]
    if cuid_scroller is None:
        raise RuntimeError("The CUID page is missing its main scroll container")
    before_scroll = cuid_scroller.canvas.yview()
    cuid_scroller.canvas.yview_scroll(5, "units")
    root.update_idletasks()
    root.update()
    after_scroll = cuid_scroller.canvas.yview()
    if after_scroll == before_scroll:
        raise RuntimeError("The CUID page did not scroll at minimum window size")
    if cuid_scroller.scrollbar.winfo_manager() != "grid":
        raise RuntimeError("The CUID scrollbar did not appear when scrolling was needed")
    tree_scrollbars = [
        child
        for child in app.material_tree.master.winfo_children()
        if child.winfo_class() == "TScrollbar"
    ]
    if not tree_scrollbars or tree_scrollbars[0].winfo_manager():
        raise RuntimeError("The material-tree scrollbar stayed visible for one item")
    cuid_scroller.canvas.yview_moveto(0.0)

    initial_scroll_height = cuid_scroller.canvas.bbox("all")[3]
    app._remember_library_sash(SimpleNamespace(y=500))
    root.after(180, root.quit)
    root.mainloop()
    expanded_scroll_height = cuid_scroller.canvas.bbox("all")[3]
    if expanded_scroll_height <= initial_scroll_height:
        raise RuntimeError("The CUID divider did not expand the page scroll region")
    if app.library_sash_position != 500:
        raise RuntimeError("The material library divider did not retain its position")
    if app.cuid_detail_card.winfo_height() < app.cuid_detail_card.winfo_reqheight():
        raise RuntimeError("The CUID write controls remain clipped below the divider")

    app._remember_library_sash(SimpleNamespace(y=180))
    root.after(180, root.quit)
    root.mainloop()
    reduced_scroll_height = cuid_scroller.canvas.bbox("all")[3]
    if reduced_scroll_height >= expanded_scroll_height:
        raise RuntimeError("The CUID divider did not shrink the page scroll region")

    # A narrow layout can make wrapped controls taller. Returning to a height
    # that fits the real controls must not retain the old Panedwindow request as
    # an empty scrollable tail.
    root.geometry("860x640")
    root.after(120, root.quit)
    root.mainloop()
    root.geometry("1180x835")
    root.after(180, root.quit)
    root.mainloop()
    expected_height = max(
        cuid_scroller.canvas.winfo_height(), cuid_scroller.content_min_height
    )
    actual_height = cuid_scroller.canvas.bbox("all")[3]
    if abs(actual_height - expected_height) > 1:
        raise RuntimeError("The CUID scroll region retained a stale enlarged height")
    if cuid_scroller.scrollbar.winfo_manager():
        raise RuntimeError("The CUID scrollbar stayed visible over an empty tail")

    # Child requested sizes must not push the native top-level geometry back
    # while a window edge is being dragged.
    root.geometry("1500x1050")
    root.after(100, root.quit)
    root.mainloop()
    root.geometry("900x700")
    root.after(180, root.quit)
    root.mainloop()
    if root.winfo_width() > 910 or root.winfo_height() > 710:
        raise RuntimeError("The main window resisted shrinking after being enlarged")

    root.geometry("1180x900")
    root.after(120, root.quit)
    root.mainloop()
    if cuid_scroller.scrollbar.winfo_manager():
        raise RuntimeError("The CUID scrollbar did not hide again after enlarging the window")

    original_url = "https://example.com/theme-preservation"
    app.url_var.set(original_url)
    app._select_mode(MODE_TYPE2)
    root.update_idletasks()
    root.update()
    if app.cuid_check_button.cget("text") != app.t("app.check_cuid"):
        raise RuntimeError("The CUID page is missing its targeted check control")
    if app.ntag_check_button.cget("text") != app.t("app.check_ndef"):
        raise RuntimeError("The NDEF page is missing its targeted check control")
    if app.ndef_read_button.cget("text") != app.t("app.read_ndef"):
        raise RuntimeError("The NDEF page is missing its read-only content control")
    if app.ntag_full_erase_button.cget("style") != "Danger.TButton":
        raise RuntimeError("Zero user memory is not rendered as the destructive action")
    if app.ntag_erase_button.winfo_width() <= app.ntag_full_erase_button.winfo_width():
        raise RuntimeError("Clear NDEF content is not larger than Zero user memory")

    app._toggle_theme()
    root.update_idletasks()
    root.update()
    _assert_theme(app, DARK)
    if app.current_mode != MODE_TYPE2:
        raise RuntimeError("Theme switching did not preserve the selected protocol")
    if app.ntag_mode.winfo_manager() != "grid":
        raise RuntimeError("The selected NDEF page is not managed")
    if app.cuid_mode.winfo_manager() or app.settings_mode.winfo_manager():
        raise RuntimeError("Inactive pages were not removed from resize layout")
    if app.url_var.get() != original_url:
        raise RuntimeError("Theme switching did not preserve form values")
    if len(app.source_items) != library_item_count:
        raise RuntimeError("Theme switching discarded the material library")

    app._change_language("en")
    root.update_idletasks()
    root.update()
    if len(app.source_items) != library_item_count:
        raise RuntimeError("Language switching discarded the material library")
    if app.url_var.get() != original_url:
        raise RuntimeError("Language switching did not preserve form values")

    initial_field_ids = [item.get("builtin") for item in app.type2_fields]
    if initial_field_ids != ["url", "brand", "filament", "purchase"]:
        raise RuntimeError("The clean NDEF editor did not load the expected fields")
    app._move_type2_field(0, 1)
    app._remove_type2_field(3)
    app._add_custom_field("text")
    custom = app.type2_fields[-1]
    custom["name_var"].set("Diameter")
    custom["value_var"].set("1.75 mm")
    reordered_ids = [item.get("builtin") for item in app.type2_fields]
    if reordered_ids != ["brand", "url", "filament", None]:
        raise RuntimeError("NDEF field move or removal did not update the ordered list")
    collected = app._collect_type2_fields()
    if [field.name for field in collected] != [
        "Brand",
        "Link",
        "Filament / colour",
        "Diameter",
    ]:
        raise RuntimeError("The NDEF editor did not preserve the displayed field order")

    app.brand_var.set("A very long field value " * 20)
    root.update_idletasks()
    root.update()

    def descendants(widget: tk.Misc) -> list[tk.Misc]:
        result: list[tk.Misc] = []
        for child in widget.winfo_children():
            result.append(child)
            result.extend(descendants(child))
        return result

    horizontal_scrollbars = [
        widget
        for widget in descendants(app.ntag_fields_frame)
        if widget.winfo_class() == "TScrollbar"
        and str(widget.cget("orient")) == "horizontal"
    ]
    if not horizontal_scrollbars or not any(
        scrollbar.winfo_manager() == "grid" for scrollbar in horizontal_scrollbars
    ):
        raise RuntimeError("Long NDEF values did not expose a horizontal scrollbar")

    app.events.put(UiEvent.progress("GUI_SMOKE_EVENT"))
    root.after(140, root.quit)
    root.mainloop()
    if app.progress_var.get() != "GUI_SMOKE_EVENT":
        raise RuntimeError("The typed GUI event queue did not update the UI")

    app.activity_bar.start(MODE_CUID)
    root.update()
    if app.activity_bar._state != "running":
        raise RuntimeError("The activity bar did not enter its running state")
    app.activity_bar.set_cancelling()
    if app.activity_bar._state != "cancelling":
        raise RuntimeError("The activity bar did not enter its cancelling state")
    app.activity_bar.stop(state="success")

    app._open_settings()
    root.update_idletasks()
    root.update()
    if app.current_mode != MODE_SETTINGS:
        raise RuntimeError("The Settings page did not open")
    if app.settings_mode.winfo_ismapped() != 1:
        raise RuntimeError("The Settings page is not visible")
    if app.settings_save_button.winfo_ismapped() != 1:
        raise RuntimeError("The Settings save button is not visible in the footer")
    save_column = int(app.settings_save_button.grid_info()["column"])
    cancel_column = int(app.cancel_button.grid_info()["column"])
    if cancel_column != save_column + 1:
        raise RuntimeError("Save and Cancel operation are not next to each other")

    if app.settings_notebook.tab(0, "text") != app.t("settings.general_tab"):
        raise RuntimeError("The first Settings tab is not named General")
    if app.clear_user_data_button.winfo_ismapped() != 1:
        raise RuntimeError("The Delete user data button is not available in General")

    dialog_checked = {"value": False}

    def close_themed_dialog() -> None:
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel):
                if child.cget("background").lower() != app.theme.palette.window.lower():
                    raise RuntimeError("The themed dialog did not use the active background")
                dialog_checked["value"] = True
                child.destroy()

    root.after(80, close_themed_dialog)
    app.dialogs.info("Theme smoke", "The modal dialog follows the dark theme.")
    if not dialog_checked["value"]:
        raise RuntimeError("The themed dialog did not open")

    text_dialog_checked = {"value": False}

    def inspect_and_close_text_dialog() -> None:
        for child in root.winfo_children():
            if not isinstance(child, tk.Toplevel):
                continue
            text_widgets = [
                widget
                for widget in descendants(child)
                if isinstance(widget, tk.Text)
            ]
            if not text_widgets:
                continue
            content = text_widgets[0].get("1.0", "end-1c")
            if "https://example.com/filament" not in content:
                raise RuntimeError("The NDEF result dialog did not expose its content")
            text_dialog_checked["value"] = True
            child.destroy()

    root.after(80, inspect_and_close_text_dialog)
    app.dialogs.text_info(
        "NDEF content",
        "Read-only result",
        "Link https://example.com/filament",
    )
    if not text_dialog_checked["value"]:
        raise RuntimeError("The copyable NDEF result dialog did not open")

    app._on_close()

    second_root = tk.Tk()
    second_app = WriterApp(second_root)
    second_root.update_idletasks()
    second_root.update()
    if len(second_app.source_items) != library_item_count:
        raise RuntimeError("The material library was not restored from disk cache")
    restored_ids = [item.get("builtin") for item in second_app.type2_fields]
    if restored_ids != ["brand", "url", "filament", None]:
        raise RuntimeError("The ordered NDEF field list was not restored from settings")
    if second_app._type2_field_name(second_app.type2_fields[-1]) != "Diameter":
        raise RuntimeError("The custom NDEF field name was not restored")
    second_app._on_close()

    settings_file = base / "BambuRFIDWriter" / "settings.json"
    legacy = json.loads(settings_file.read_text(encoding="utf-8"))
    legacy.pop("ntag_fields", None)
    legacy["ntag_brand"] = "Legacy Brand"
    legacy["ntag_custom_fields"] = json.dumps(
        [{"name": "Legacy field", "value": "Legacy value", "write_name": True}]
    )
    settings_file.write_text(json.dumps(legacy), encoding="utf-8")

    third_root = tk.Tk()
    third_app = WriterApp(third_root)
    third_root.update_idletasks()
    third_root.update()
    migrated_ids = [item.get("builtin") for item in third_app.type2_fields]
    if migrated_ids != ["url", "brand", "filament", "purchase", None]:
        raise RuntimeError("Legacy fixed NDEF settings were not migrated")
    if third_app.brand_var.get() != "Legacy Brand":
        raise RuntimeError("Legacy built-in NDEF values were not migrated")
    if third_app._type2_field_name(third_app.type2_fields[-1]) != "Legacy field":
        raise RuntimeError("Legacy custom NDEF fields were not migrated")
    third_app._on_close()

    fourth_root = tk.Tk()
    fourth_app = WriterApp(fourth_root)
    fourth_root.update_idletasks()
    fourth_root.update()
    fourth_app.dialogs.confirm = lambda *_args, **_kwargs: True
    fourth_app._clear_user_data()
    if (base / "BambuRFIDWriter").exists():
        raise RuntimeError("Delete user data left the application data directory behind")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="BambuRFIDGuiSmoke_") as directory:
        previous = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = directory
        try:
            run_smoke_test(Path(directory))
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous
    print("GUI smoke test passed in light and dark themes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
