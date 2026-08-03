from __future__ import annotations

import json
import tkinter as tk

from ..options import (
    MfcSourceChecks,
    MfcWriteOptions,
    NTAG_METHOD_RAW,
    PROFILE_CUSTOM,
    PROFILE_RECOMMENDED,
    TimeoutOptions,
    Type2EraseOptions,
    Type2WriteOptions,
    bool_from_settings,
    detect_profile,
    int_from_settings,
    mfc_profile,
    type2_erase_profile,
    type2_write_profile,
)


class OperationSettingsMixin:
    """Map persisted GUI settings to immutable workflow option objects."""

    @staticmethod
    def _setting_bool(
        settings: dict[str, str], key: str, default: bool
    ) -> bool:
        return bool_from_settings(settings, key, default)

    def _init_operation_settings(self, settings: dict[str, str]) -> None:
        def b(key: str, default: bool) -> tk.BooleanVar:
            return tk.BooleanVar(value=bool_from_settings(settings, key, default))

        self.mfc_profile_var = tk.StringVar(value=settings.get("mfc_profile", PROFILE_RECOMMENDED))
        self.mfc_option_vars = {
            "source_dump_size": b("mfc_source_dump_size", True),
            "source_key_size": b("mfc_source_key_size", True),
            "source_bcc": b("mfc_source_bcc", True),
            "source_trailer_keys": b("mfc_source_trailer_keys", True),
            "source_access_bits": b("mfc_source_access_bits", True),
            "source_filename_uid": b("mfc_source_filename_uid", True),
            "client_firmware": b("mfc_client_firmware", True),
            "tag_type": b("mfc_tag_type", True),
            "magic_type": b("mfc_magic_type", True),
            "default_keys": b("mfc_default_keys", True),
            "backup": b("mfc_backup", True),
            "target_stability": b("mfc_target_stability", True),
            "verify_dump": b("mfc_verify_dump", True),
            "verify_uid": b("mfc_verify_uid", True),
        }

        self.ntag_profile_var = tk.StringVar(
            value=settings.get("ntag_profile", PROFILE_RECOMMENDED)
        )
        self.ntag_method_var = tk.StringVar(value=settings.get("ntag_method", NTAG_METHOD_RAW))
        self.ntag_option_vars = {
            "client_firmware": b("ntag_client_firmware", True),
            "tag_type": b("ntag_tag_type", True),
            "static_lock": b("ntag_static_lock", True),
            "dynamic_lock": b("ntag_dynamic_lock", True),
            "auth0": b("ntag_auth0", True),
            "ecc_signature": b("ntag_ecc_signature", False),
            "backup": b("ntag_backup", True),
            "target_stability": b("ntag_target_stability", True),
            "two_phase": b("ntag_two_phase", True),
            "precommit_verify": b("ntag_precommit_verify", True),
            "final_verify": b("ntag_final_verify", True),
            "protected_verify": b("ntag_protected_verify", True),
        }

        self.erase_profile_var = tk.StringVar(
            value=settings.get("erase_profile", PROFILE_RECOMMENDED)
        )
        self.erase_method_var = tk.StringVar(value=settings.get("erase_method", NTAG_METHOD_RAW))
        self.erase_option_vars = {
            "client_firmware": b("erase_client_firmware", True),
            "tag_type": b("erase_tag_type", True),
            "static_lock": b("erase_static_lock", True),
            "dynamic_lock": b("erase_dynamic_lock", True),
            "auth0": b("erase_auth0", True),
            "ecc_signature": b("erase_ecc_signature", False),
            "backup": b("erase_backup", True),
            "target_stability": b("erase_target_stability", True),
            "scan_nonzero_pages": b("erase_scan_nonzero_pages", True),
            "final_verify": b("erase_final_verify", True),
            "protected_verify": b("erase_protected_verify", True),
        }

        self.timeout_vars = {
            "startup": tk.StringVar(value=str(int_from_settings(settings, "timeout_startup", 45))),
            "idle": tk.StringVar(value=str(int_from_settings(settings, "timeout_idle", 90))),
            "command": tk.StringVar(value=str(int_from_settings(settings, "timeout_command", 300))),
            "operation": tk.StringVar(
                value=str(int_from_settings(settings, "timeout_operation", 600))
            ),
        }

        # A non-Custom profile is authoritative. Re-apply its current preset so
        # settings saved by an older version cannot silently retain obsolete
        # combinations after profile definitions change.
        if self.mfc_profile_var.get() != PROFILE_CUSTOM:
            preset = mfc_profile(self.mfc_profile_var.get())
            mfc_values = {
                "source_dump_size": preset.source.dump_size,
                "source_key_size": preset.source.key_size,
                "source_bcc": preset.source.bcc,
                "source_trailer_keys": preset.source.trailer_keys,
                "source_access_bits": preset.source.access_bits,
                "source_filename_uid": preset.source.filename_uid,
                "client_firmware": preset.client_firmware,
                "tag_type": preset.tag_type,
                "magic_type": preset.magic_type,
                "default_keys": preset.default_keys,
                "backup": preset.backup,
                "target_stability": preset.target_stability,
                "verify_dump": preset.verify_dump,
                "verify_uid": preset.verify_uid,
            }
            for key, value in mfc_values.items():
                self.mfc_option_vars[key].set(value)
        if self.ntag_profile_var.get() != PROFILE_CUSTOM:
            preset = type2_write_profile(self.ntag_profile_var.get())
            self.ntag_method_var.set(preset.method)
            for key, var in self.ntag_option_vars.items():
                var.set(getattr(preset, key))
        if self.erase_profile_var.get() != PROFILE_CUSTOM:
            preset = type2_erase_profile(self.erase_profile_var.get())
            self.erase_method_var.set(preset.method)
            for key, var in self.erase_option_vars.items():
                var.set(getattr(preset, key))

        self.mfc_profile_var.set(
            detect_profile(self._current_mfc_options(), mfc_profile)
        )
        self.ntag_profile_var.set(
            detect_profile(self._current_type2_options(), type2_write_profile)
        )
        self.erase_profile_var.set(
            detect_profile(self._current_erase_options(), type2_erase_profile)
        )

    def _current_timeouts(self) -> TimeoutOptions:
        values: list[int] = []
        for key in ("startup", "idle", "command", "operation"):
            try:
                value = int(self.timeout_vars[key].get().strip())
            except ValueError as exc:
                raise ValueError(self.t("app.timeout_invalid")) from exc
            if value < 0:
                raise ValueError(self.t("app.timeout_invalid"))
            values.append(value)
        return TimeoutOptions(*values)

    def _current_mfc_options(self) -> MfcWriteOptions:
        v = self.mfc_option_vars
        return MfcWriteOptions(
            profile=self.mfc_profile_var.get(),
            source=MfcSourceChecks(
                v["source_dump_size"].get(), v["source_key_size"].get(),
                v["source_bcc"].get(), v["source_trailer_keys"].get(),
                v["source_access_bits"].get(), v["source_filename_uid"].get(),
            ),
            client_firmware=v["client_firmware"].get(), tag_type=v["tag_type"].get(),
            magic_type=v["magic_type"].get(), default_keys=v["default_keys"].get(),
            backup=v["backup"].get(), target_stability=v["target_stability"].get(),
            verify_dump=v["verify_dump"].get(), verify_uid=v["verify_uid"].get(),
        )

    def _current_type2_options(self) -> Type2WriteOptions:
        v = self.ntag_option_vars
        return Type2WriteOptions(
            profile=self.ntag_profile_var.get(), method=self.ntag_method_var.get(),
            **{key: var.get() for key, var in v.items()},
        )

    def _current_erase_options(self) -> Type2EraseOptions:
        v = self.erase_option_vars
        return Type2EraseOptions(
            profile=self.erase_profile_var.get(), method=self.erase_method_var.get(),
            **{key: var.get() for key, var in v.items()},
        )

    @staticmethod
    def _strict_bool(value: object, default: bool = True) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    def _init_type2_fields(self, settings: dict[str, str], *, default_date: str) -> None:
        """Create editable NDEF fields and migrate settings from pre-0.9 releases."""
        self.brand_var = tk.StringVar(value=settings.get("ntag_brand", "Bambu Lab"))
        self.filament_var = tk.StringVar(value=settings.get("ntag_filament", ""))
        self.purchase_var = tk.StringVar(
            value=settings.get("ntag_purchase", default_date)
        )
        self.url_var = tk.StringVar(value=settings.get("ntag_url", "https://"))
        self.brand_name_var = tk.BooleanVar(
            value=self._setting_bool(settings, "ntag_brand_write_name", False)
        )
        self.filament_name_var = tk.BooleanVar(
            value=self._setting_bool(settings, "ntag_filament_write_name", False)
        )
        self.purchase_name_var = tk.BooleanVar(
            value=self._setting_bool(settings, "ntag_purchase_write_name", True)
        )
        self.url_name_var = tk.BooleanVar(value=False)
        self.type2_fields = self._load_type2_fields(
            settings.get("ntag_fields", ""),
            legacy_custom_raw=settings.get("ntag_custom_fields", "[]"),
        )

    def _builtin_type2_field(self, field_id: str) -> dict[str, object] | None:
        mapping = {
            "url": ("app.url_name", self.url_var, self.url_name_var, "uri"),
            "brand": ("app.brand_name", self.brand_var, self.brand_name_var, "text"),
            "filament": (
                "app.filament_name",
                self.filament_var,
                self.filament_name_var,
                "text",
            ),
            "purchase": (
                "app.purchase_name",
                self.purchase_var,
                self.purchase_name_var,
                "text",
            ),
        }
        definition = mapping.get(field_id)
        if definition is None:
            return None
        label_key, value_var, write_var, kind = definition
        return {
            "builtin": field_id,
            "label_key": label_key,
            "name_var": None,
            "value_var": value_var,
            "write_var": write_var,
            "kind": kind,
        }

    def _custom_type2_field(
        self,
        *,
        name: str,
        value: str = "",
        write_name: bool = True,
        kind: str = "text",
    ) -> dict[str, object]:
        normalized_kind = "uri" if str(kind).lower() == "uri" else "text"
        return {
            "builtin": None,
            "label_key": None,
            "name_var": tk.StringVar(value=name),
            "value_var": tk.StringVar(value=value),
            "write_var": tk.BooleanVar(
                value=False if normalized_kind == "uri" else bool(write_name)
            ),
            "kind": normalized_kind,
        }

    def _load_type2_fields(
        self, raw: str, *, legacy_custom_raw: str
    ) -> list[dict[str, object]]:
        """Load the ordered field list, falling back to the legacy fixed layout."""
        try:
            data = json.loads(raw) if raw else None
        except (TypeError, json.JSONDecodeError):
            data = None

        if isinstance(data, list):
            result: list[dict[str, object]] = []
            used_builtins: set[str] = set()
            for item in data:
                if not isinstance(item, dict):
                    continue
                builtin = str(item.get("builtin") or "").strip().lower()
                if builtin and builtin not in used_builtins:
                    field = self._builtin_type2_field(builtin)
                    if field is not None:
                        field["value_var"].set(str(item.get("value", "")))
                        field["write_var"].set(
                            False
                            if field["kind"] == "uri"
                            else self._strict_bool(item.get("write_name"), True)
                        )
                        result.append(field)
                        used_builtins.add(builtin)
                        continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                result.append(
                    self._custom_type2_field(
                        name=name,
                        value=str(item.get("value", "")),
                        write_name=self._strict_bool(item.get("write_name"), True),
                        kind=str(item.get("kind", "text")),
                    )
                )
            return result

        result = [
            self._builtin_type2_field("url"),
            self._builtin_type2_field("brand"),
            self._builtin_type2_field("filament"),
            self._builtin_type2_field("purchase"),
        ]
        fields = [field for field in result if field is not None]
        try:
            legacy_data = json.loads(legacy_custom_raw)
        except (TypeError, json.JSONDecodeError):
            legacy_data = []
        if isinstance(legacy_data, list):
            for item in legacy_data:
                if not isinstance(item, dict):
                    continue
                fields.append(
                    self._custom_type2_field(
                        name=str(item.get("name", self.t("app.custom_field_default"))),
                        value=str(item.get("value", "")),
                        write_name=self._strict_bool(item.get("write_name"), True),
                    )
                )
        return fields

    def _serialize_type2_fields(self) -> str:
        data: list[dict[str, object]] = []
        for item in self.type2_fields:
            name_var = item.get("name_var")
            data.append(
                {
                    "builtin": item.get("builtin"),
                    "name": "" if name_var is None else str(name_var.get()),
                    "value": str(item["value_var"].get()),
                    "write_name": bool(item["write_var"].get()),
                    "kind": str(item.get("kind", "text")),
                }
            )
        return json.dumps(data, ensure_ascii=False)

