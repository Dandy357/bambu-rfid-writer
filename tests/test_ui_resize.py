from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UiResizeRegressionTests(unittest.TestCase):
    def test_only_the_active_primary_page_is_managed(self) -> None:
        source = (ROOT / "bambu_rfid_diag" / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        select_mode = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_select_mode"
        )
        calls = [
            node.func.attr
            for node in ast.walk(select_mode)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        self.assertIn("grid_remove", calls)
        self.assertIn("grid", calls)
        self.assertNotIn("tkraise", calls)

    def test_cuid_page_does_not_render_the_generic_gen2_warning_card(self) -> None:
        source = (
            ROOT / "bambu_rfid_diag" / "ui" / "mifare_view.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("app.cuid_warning", source)

    def test_resize_callbacks_are_debounced(self) -> None:
        app_source = (ROOT / "bambu_rfid_diag" / "app.py").read_text(encoding="utf-8")
        widgets_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "widgets.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.callbacks.schedule(label, 45, apply_width", app_source)
        self.assertIn("self.after(30, self._sync_scrollregion)", widgets_source)
        self.assertIn("self.after(20, self._sync_width)", widgets_source)
        self.assertIn(
            'self.content.bind("<Configure>", self._schedule_content_layout)',
            widgets_source,
        )

    def test_cuid_divider_refreshes_the_outer_scroll_layout(self) -> None:
        source = (
            ROOT / "bambu_rfid_diag" / "ui" / "mifare_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"<B1-Motion>", self._on_library_sash_motion', source)
        self.assertIn("self.cuid_write_content.rowconfigure(", source)
        self.assertIn("self.cuid_write_scroller.set_content_min_height(", source)

    def test_scrollbars_hide_until_their_content_overflows(self) -> None:
        widgets_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "widgets.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class AutoHideScrollbar(ttk.Scrollbar):", widgets_source)
        self.assertIn("scrolling_needed =", widgets_source)
        self.assertIn("self.grid_remove()", widgets_source)

        scrollbar_views = (
            ROOT / "bambu_rfid_diag" / "ui" / "mifare_view.py",
            ROOT / "bambu_rfid_diag" / "ui" / "type2_view.py",
            ROOT / "bambu_rfid_diag" / "ui" / "results.py",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in scrollbar_views)
        self.assertNotIn("ttk.Scrollbar(", combined)
        self.assertIn("AutoHideScrollbar(", combined)


    def test_fill_height_scroller_uses_a_logical_minimum(self) -> None:
        widgets_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "widgets.py"
        ).read_text(encoding="utf-8")
        mifare_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "mifare_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def set_content_min_height(self, height: int)", widgets_source)
        self.assertIn(
            "target_height = max(self._pending_height, self._content_min_height)",
            widgets_source,
        )
        self.assertNotIn(
            "target_height = max(self._pending_height, requested)", widgets_source
        )
        self.assertIn(
            "self.cuid_write_scroller.set_content_min_height(content_min_height)",
            mifare_source,
        )

    def test_top_level_size_is_not_driven_by_scrollbar_churn(self) -> None:
        app_source = (ROOT / "bambu_rfid_diag" / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.root.resizable(True, True)", app_source)
        self.assertIn("self.root.pack_propagate(False)", app_source)

    def test_settings_save_button_shares_the_operation_footer(self) -> None:
        app_source = (ROOT / "bambu_rfid_diag" / "app.py").read_text(encoding="utf-8")
        settings_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "settings_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.settings_save_button = ttk.Button(", app_source)
        self.assertIn("self.cancel_button.grid(row=0, column=2", app_source)
        self.assertNotIn("buttons = ttk.Frame(outer)", settings_source)

    def test_general_settings_and_user_data_controls_are_present(self) -> None:
        settings_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "settings_view.py"
        ).read_text(encoding="utf-8")
        self.assertIn('tab_frame("settings.general_tab")', settings_source)
        self.assertIn("command=self._clear_user_data", settings_source)
        self.assertIn("clear_user_data_directory()", settings_source)
        self.assertIn("self.root.destroy()", settings_source)

    def test_protocol_specific_checks_and_ndef_reader_are_exposed(self) -> None:
        mifare_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "mifare_view.py"
        ).read_text(encoding="utf-8")
        type2_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "type2_view.py"
        ).read_text(encoding="utf-8")
        operations_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "operations.py"
        ).read_text(encoding="utf-8")
        self.assertIn('self.t("app.check_cuid")', mifare_source)
        self.assertIn('self.t("app.check_ndef")', type2_source)
        self.assertIn("command=self._start_ndef_read", type2_source)
        self.assertIn("expected_family=", operations_source)
        self.assertIn("UiEvent.ndef_read_done", operations_source)

    def test_ndef_value_entries_have_horizontal_scrollbars(self) -> None:
        editor_source = (
            ROOT / "bambu_rfid_diag" / "ui" / "type2_editor.py"
        ).read_text(encoding="utf-8")
        self.assertIn('orient="horizontal"', editor_source)
        self.assertIn("command=value_entry.xview", editor_source)
        self.assertIn("value_entry.configure(xscrollcommand=value_scroll.set)", editor_source)


if __name__ == "__main__":
    unittest.main()
