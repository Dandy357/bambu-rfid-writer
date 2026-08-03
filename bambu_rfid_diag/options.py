from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Mapping


PROFILE_FAST = "fast"
PROFILE_RECOMMENDED = "recommended"
PROFILE_THOROUGH = "thorough"
PROFILE_CUSTOM = "custom"
PROFILES = (PROFILE_FAST, PROFILE_RECOMMENDED, PROFILE_THOROUGH, PROFILE_CUSTOM)

NTAG_METHOD_RAW = "raw"
NTAG_METHOD_RESTORE = "restore"
NTAG_METHOD_WRBL = "wrbl"
NTAG_METHODS = (NTAG_METHOD_RAW, NTAG_METHOD_RESTORE, NTAG_METHOD_WRBL)

ERASE_SCOPE_NDEF = "ndef"
ERASE_SCOPE_USER = "user"
ERASE_SCOPES = (ERASE_SCOPE_NDEF, ERASE_SCOPE_USER)


@dataclass(frozen=True, slots=True)
class TimeoutOptions:
    startup_seconds: int = 45
    idle_seconds: int = 90
    command_seconds: int = 300
    operation_seconds: int = 600

    def normalized(self) -> "TimeoutOptions":
        return TimeoutOptions(*(_nonnegative(getattr(self, f.name)) for f in fields(self)))


@dataclass(frozen=True, slots=True)
class MfcSourceChecks:
    dump_size: bool = True
    key_size: bool = True
    bcc: bool = True
    trailer_keys: bool = True
    access_bits: bool = True
    filename_uid: bool = True


@dataclass(frozen=True, slots=True)
class MfcWriteOptions:
    profile: str = PROFILE_RECOMMENDED
    source: MfcSourceChecks = MfcSourceChecks()
    client_firmware: bool = True
    tag_type: bool = True
    magic_type: bool = True
    default_keys: bool = True
    backup: bool = True
    target_stability: bool = True
    verify_dump: bool = True
    verify_uid: bool = True


@dataclass(frozen=True, slots=True)
class Type2WriteOptions:
    profile: str = PROFILE_RECOMMENDED
    method: str = NTAG_METHOD_RAW
    client_firmware: bool = True
    tag_type: bool = True
    static_lock: bool = True
    dynamic_lock: bool = True
    auth0: bool = True
    ecc_signature: bool = False
    backup: bool = True
    target_stability: bool = True
    two_phase: bool = True
    precommit_verify: bool = True
    final_verify: bool = True
    protected_verify: bool = True


@dataclass(frozen=True, slots=True)
class Type2EraseOptions:
    profile: str = PROFILE_RECOMMENDED
    method: str = NTAG_METHOD_RAW
    scope: str = ERASE_SCOPE_NDEF
    client_firmware: bool = True
    tag_type: bool = True
    static_lock: bool = True
    dynamic_lock: bool = True
    auth0: bool = True
    ecc_signature: bool = False
    backup: bool = True
    target_stability: bool = True
    scan_nonzero_pages: bool = True
    final_verify: bool = True
    protected_verify: bool = True


def mfc_profile(name: str) -> MfcWriteOptions:
    name = _profile(name)
    if name == PROFILE_FAST:
        return MfcWriteOptions(
            profile=name,
            source=MfcSourceChecks(),
            client_firmware=False,
            tag_type=True,
            magic_type=True,
            default_keys=True,
            backup=False,
            target_stability=False,
            verify_dump=False,
            verify_uid=False,
        )
    if name == PROFILE_THOROUGH:
        return MfcWriteOptions(profile=name)
    return MfcWriteOptions(
        profile=PROFILE_RECOMMENDED,
        client_firmware=True,
        backup=True,
        verify_uid=False,
    )


def type2_write_profile(name: str) -> Type2WriteOptions:
    name = _profile(name)
    if name == PROFILE_FAST:
        return Type2WriteOptions(
            profile=name,
            method=NTAG_METHOD_RAW,
            client_firmware=False,
            tag_type=True,
            static_lock=True,
            dynamic_lock=True,
            auth0=True,
            ecc_signature=False,
            backup=False,
            target_stability=False,
            two_phase=False,
            precommit_verify=False,
            final_verify=False,
            protected_verify=False,
        )
    if name == PROFILE_THOROUGH:
        return Type2WriteOptions(profile=name, ecc_signature=True)
    return Type2WriteOptions(
        profile=PROFILE_RECOMMENDED,
        client_firmware=True,
        ecc_signature=False,
        precommit_verify=False,
    )


def type2_erase_profile(name: str) -> Type2EraseOptions:
    name = _profile(name)
    if name == PROFILE_FAST:
        return Type2EraseOptions(
            profile=name,
            method=NTAG_METHOD_RAW,
            client_firmware=False,
            tag_type=True,
            static_lock=True,
            dynamic_lock=True,
            auth0=True,
            ecc_signature=False,
            backup=False,
            target_stability=False,
            scan_nonzero_pages=False,
            final_verify=False,
            protected_verify=False,
        )
    if name == PROFILE_THOROUGH:
        return Type2EraseOptions(profile=name, ecc_signature=True)
    return Type2EraseOptions(
        profile=PROFILE_RECOMMENDED,
        client_firmware=True,
        ecc_signature=False,
    )


def detect_profile(value, profile_factory) -> str:
    """Return a preset name if values exactly match it, otherwise custom."""
    for name in (PROFILE_FAST, PROFILE_RECOMMENDED, PROFILE_THOROUGH):
        preset = profile_factory(name)
        if replace(value, profile=name) == preset:
            return name
    return PROFILE_CUSTOM


def bool_from_settings(settings: Mapping[str, str], key: str, default: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def int_from_settings(settings: Mapping[str, str], key: str, default: int) -> int:
    raw = settings.get(key)
    if raw is None:
        return default
    try:
        return _nonnegative(int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _profile(name: str) -> str:
    return name if name in PROFILES else PROFILE_RECOMMENDED


def _nonnegative(value: int) -> int:
    return max(0, int(value))

# Canonical NFC Type 2 terminology. Legacy NTAG names remain supported for
# saved settings and third-party imports from earlier beta versions.
TYPE2_METHOD_RAW = NTAG_METHOD_RAW
TYPE2_METHOD_RESTORE = NTAG_METHOD_RESTORE
TYPE2_METHOD_WRBL = NTAG_METHOD_WRBL
TYPE2_METHODS = NTAG_METHODS
NtagWriteOptions = Type2WriteOptions
NtagEraseOptions = Type2EraseOptions
ntag_write_profile = type2_write_profile
ntag_erase_profile = type2_erase_profile
