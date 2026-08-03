from __future__ import annotations

from pathlib import Path
from tkinter import END, filedialog

from ..material_library import (
    MaterialNode,
    STATUS_INVALID,
    STATUS_READY,
    STATUS_UNVERIFIED,
    STATUS_WARNING,
    clear_material_library_cache,
    flatten_sources,
    load_cached_material_library,
    refresh_material_node,
    scan_material_library,
)
from ..sources import MfcSource, SourceValidationError, load_mfc_source


class MaterialLibraryMixin:
    """Present, restore, and refresh the material-library tree."""

    def _choose_library(self) -> None:
        initial = self.material_library_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(
            title=self.t("app.choose_library_title"),
            initialdir=initial if Path(initial).exists() else str(Path.home()),
            mustexist=True,
            parent=self.root,
        )
        if selected:
            self.material_library_var.set(selected)
            self.library_nodes = []
            self.library_selected_path = None
            self._clear_material_tree()
            clear_material_library_cache()
            self.library_status_var.set(self.t("app.library_ready_to_load"))
            self._save_current_settings()

    def _clear_material_tree(self) -> None:
        self.source_items.clear()
        if not hasattr(self, "material_tree"):
            return
        for item in self.material_tree.get_children():
            self.material_tree.delete(item)

    def _load_material_library(self, show_dialog: bool) -> bool:
        value = self.material_library_var.get().strip()
        self._clear_material_tree()
        if not value:
            self.library_nodes = []
            self.library_status_var.set(self.t("app.library_prompt"))
            return False
        self.library_status_var.set(self.t("app.library_scanning"))
        self.root.update_idletasks()
        try:
            nodes = scan_material_library(value, self.locale)
        except ValueError as exc:
            self.library_nodes = []
            self.library_status_var.set(f"✕ {exc}")
            if show_dialog:
                self.dialogs.error(self.t("app.invalid_library_title"), str(exc))
            return False
        root = Path(value).expanduser().resolve()
        self.material_library_var.set(str(root))
        self.library_nodes = nodes
        self._populate_material_tree(nodes)
        self._save_current_settings()
        if not nodes:
            self.library_status_var.set(self.t("app.library_empty"))
            return False
        count = len(flatten_sources(nodes))
        self.library_status_var.set(
            self.t("app.library_loaded", materials=len(nodes), tags=count)
        )
        return True

    def _restore_material_library_from_cache(self) -> bool:
        value = self.material_library_var.get().strip()
        if not value:
            return False
        nodes = load_cached_material_library(value, self.locale)
        if nodes is None:
            return False
        self.library_nodes = nodes
        self._populate_material_tree(nodes)
        count = len(flatten_sources(nodes))
        self.library_status_var.set(
            self.t("app.library_loaded_cache", materials=len(nodes), tags=count)
        )
        return True

    def _prepare_material_library_for_locale_change(self) -> None:
        for node in flatten_sources(self.library_nodes):
            node.cached = True
            node.detail = ""

    def _restore_material_library_view(self) -> None:
        if self.library_nodes:
            self._populate_material_tree(self.library_nodes)
            count = len(flatten_sources(self.library_nodes))
            self.library_status_var.set(
                self.t("app.library_loaded_memory", materials=len(self.library_nodes), tags=count)
            )
        elif self.material_library_var.get().strip():
            self.library_status_var.set(self.t("app.library_ready_to_load"))

    def _populate_material_tree(self, nodes: list[MaterialNode]) -> None:
        self._clear_material_tree()
        for node in nodes:
            self._insert_material_node("", node)
        selected_path = self.library_selected_path
        if selected_path is None and self.source_folder_var.get().strip():
            try:
                selected_path = Path(self.source_folder_var.get()).expanduser().resolve()
            except OSError:
                selected_path = None
        if selected_path is None:
            return
        for item, node in self.source_items.items():
            if node.path == selected_path:
                self.material_tree.selection_set(item)
                self.material_tree.focus(item)
                self.material_tree.see(item)
                break

    def _status_key(self, node: MaterialNode) -> str:
        return {
            STATUS_READY: "app.library_status_ready",
            STATUS_WARNING: "app.library_status_warning",
            STATUS_INVALID: "app.library_status_invalid",
            STATUS_UNVERIFIED: "app.library_status_unverified",
        }.get(node.status, "app.library_status_unverified")

    def _status_icon_name(self, node: MaterialNode) -> str:
        return (
            "ok"
            if node.status == STATUS_READY
            else "warning"
            if node.status == STATUS_WARNING
            else "error"
            if node.status == STATUS_INVALID
            else "skipped"
        )

    def _insert_material_node(self, parent: str, node: MaterialNode) -> int:
        if node.is_source:
            item = self.material_tree.insert(
                parent,
                END,
                text=node.name,
                image=self.theme.status_icon(self._status_icon_name(node)),
                values=(
                    self.t(self._status_key(node)),
                    node.authoritative_uid or node.uid_hex or "",
                ),
                tags=(node.status,),
            )
            self.source_items[item] = node
            return 1
        item = self.material_tree.insert(
            parent,
            END,
            text=node.name,
            image=self.theme.icon("folder", size=20),
            values=(self.t("app.folder"), ""),
        )
        count = 0
        for child in node.children:
            count += self._insert_material_node(item, child)
        return count

    def _update_material_item(self, item: str, node: MaterialNode) -> None:
        self.material_tree.item(
            item,
            image=self.theme.status_icon(self._status_icon_name(node)),
            values=(
                self.t(self._status_key(node)),
                node.authoritative_uid or node.uid_hex or "",
            ),
            tags=(node.status,),
        )

    def _on_material_selected(self, _event: object | None = None) -> None:
        selected = self.material_tree.selection()
        if not selected:
            return
        item = selected[0]
        candidate = self.source_items.get(item)
        if candidate is None:
            self.loaded_source = None
            self.library_selected_path = None
            self.source_status_var.set(self.t("app.select_scanned_tag"))
            return
        if candidate.cached and not candidate.detail:
            refresh_material_node(candidate, self.locale)
            self._update_material_item(item, candidate)
        self.loaded_source = None
        self.library_selected_path = candidate.path
        self.source_folder_var.set(str(candidate.path))
        status = self.t(self._status_key(candidate))
        detail = candidate.detail or self.t(
            "app.library_cached_detail",
            uid=candidate.authoritative_uid or candidate.uid_hex or "",
        )
        self.source_status_var.set(
            self.t(
                "app.source_quick_detail",
                status=status,
                detail=detail,
            )
        )
        self._save_current_settings()

    def _choose_source(self) -> None:
        initial = self.source_folder_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(
            title=self.t("app.choose_source_title"),
            initialdir=initial if Path(initial).exists() else str(Path.home()),
            mustexist=True,
            parent=self.root,
        )
        if selected:
            self.source_folder_var.set(selected)
            self.library_selected_path = Path(selected).expanduser().resolve()
            self.loaded_source = None
            self.source_status_var.set(self.t("app.source_pending_validation"))
            self._save_current_settings()

    def _validate_source(self, show_dialog: bool) -> bool:
        value = self.source_folder_var.get().strip()
        if not value:
            self.loaded_source = None
            self.source_status_var.set(self.t("app.source_prompt"))
            return False
        try:
            source = load_mfc_source(value, self.locale, self._current_mfc_options().source)
        except SourceValidationError as exc:
            self.loaded_source = None
            self.source_status_var.set(f"✕ {exc}")
            if show_dialog:
                self.dialogs.error(self.t("app.invalid_source_title"), str(exc))
            return False
        self.loaded_source = source
        self.source_folder_var.set(str(source.folder))
        self.library_selected_path = source.folder
        self._set_source_status(source)
        return True

    def _set_source_status(self, source: MfcSource) -> None:
        self.source_status_var.set(
            self.t(
                "app.source_valid",
                label=source.label,
                uid=source.uid_hex,
                dump=source.dump_path.name,
                key_file=source.key_path.name,
                sha=source.sha256[:16],
            )
        )
