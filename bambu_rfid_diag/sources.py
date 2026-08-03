from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .i18n import Translator, normalize_locale
from .options import MfcSourceChecks


class SourceValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MfcSource:
    folder: Path
    dump_path: Path
    key_path: Path
    dump_data: bytes
    key_data: bytes
    uid: bytes
    sha256: str
    label: str

    @property
    def uid_hex(self) -> str:
        return self.uid.hex().upper()


def _direct_bin_files(folder: Path, tr: Translator) -> list[Path]:
    try:
        return sorted(
            (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".bin"),
            key=lambda path: path.name.lower(),
        )
    except OSError as exc:
        raise SourceValidationError(tr.t("source.folder_read", error=exc)) from exc


def _pick_exactly_one(candidates: list[Path], kind: str, tr: Translator) -> Path:
    if not candidates:
        raise SourceValidationError(tr.t("source.none_found", kind=kind))
    if len(candidates) > 1:
        names = ", ".join(path.name for path in candidates[:5])
        suffix = "…" if len(candidates) > 5 else ""
        raise SourceValidationError(
            tr.t("source.multiple_found", kind=kind, names=names, suffix=suffix)
        )
    return candidates[0]


def _valid_access_bits(access: bytes) -> bool:
    if len(access) != 3:
        return False
    byte6, byte7, byte8 = access
    inv_c1 = byte6 & 0x0F
    inv_c2 = (byte6 >> 4) & 0x0F
    inv_c3 = byte7 & 0x0F
    c1 = (byte7 >> 4) & 0x0F
    c2 = byte8 & 0x0F
    c3 = (byte8 >> 4) & 0x0F
    return (
        (c1 ^ inv_c1) == 0x0F
        and (c2 ^ inv_c2) == 0x0F
        and (c3 ^ inv_c3) == 0x0F
    )


def load_mfc_source(
    selected_folder: str | Path,
    locale: str = "en",
    checks: MfcSourceChecks | None = None,
) -> MfcSource:
    tr = Translator(normalize_locale(locale))
    checks = checks or MfcSourceChecks()
    folder = Path(selected_folder).expanduser().resolve()
    if not folder.is_dir():
        raise SourceValidationError(tr.t("source.not_folder"))

    files = _direct_bin_files(folder, tr)
    dump_candidates = [
        path
        for path in files
        if "dump" in path.stem.lower() and not path.stem.lower().startswith("bambu_verify_")
    ]
    key_candidates = [path for path in files if "key" in path.stem.lower()]
    dump_path = _pick_exactly_one(dump_candidates, tr.t("source.dump_kind"), tr)
    key_path = _pick_exactly_one(key_candidates, tr.t("source.key_kind"), tr)

    try:
        dump_data = dump_path.read_bytes()
        key_data = key_path.read_bytes()
    except OSError as exc:
        raise SourceValidationError(tr.t("source.files_read", error=exc)) from exc

    if checks.dump_size and len(dump_data) != 1024:
        raise SourceValidationError(tr.t("source.dump_size", bytes=len(dump_data)))
    if checks.key_size and len(key_data) != 192:
        raise SourceValidationError(tr.t("source.key_size", bytes=len(key_data)))

    uid = dump_data[:4]
    if checks.bcc:
        if len(dump_data) < 5:
            raise SourceValidationError(tr.t("source.dump_size", bytes=len(dump_data)))
        expected_bcc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
        if dump_data[4] != expected_bcc:
            raise SourceValidationError(tr.t("source.invalid_bcc"))

    if checks.trailer_keys or checks.access_bits:
        if len(dump_data) < 1024 or (checks.trailer_keys and len(key_data) < 192):
            if len(dump_data) < 1024:
                raise SourceValidationError(tr.t("source.dump_size", bytes=len(dump_data)))
            raise SourceValidationError(tr.t("source.key_size", bytes=len(key_data)))
        for sector in range(16):
            trailer_offset = (sector * 4 + 3) * 16
            trailer = dump_data[trailer_offset : trailer_offset + 16]
            if checks.trailer_keys:
                key_a = key_data[sector * 6 : sector * 6 + 6]
                key_b_offset = 16 * 6 + sector * 6
                key_b = key_data[key_b_offset : key_b_offset + 6]
                if trailer[:6] != key_a or trailer[10:16] != key_b:
                    raise SourceValidationError(tr.t("source.key_mismatch", sector=sector))
            if checks.access_bits and not _valid_access_bits(trailer[6:9]):
                raise SourceValidationError(
                    tr.t(
                        "source.invalid_access",
                        sector=sector,
                        access=trailer[6:9].hex().upper(),
                    )
                )

    if checks.filename_uid:
        if len(uid) != 4:
            raise SourceValidationError(tr.t("source.dump_size", bytes=len(dump_data)))
        uid_tokens: set[str] = set()
        for path in (dump_path, key_path):
            uid_tokens.update(re.findall(r"(?i)(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])", path.stem))
        if uid_tokens and any(token.upper() != uid.hex().upper() for token in uid_tokens):
            raise SourceValidationError(tr.t("source.uid_filename", uid=uid.hex().upper()))

    digest = hashlib.sha256(dump_data).hexdigest().upper()
    label_parts = [part for part in folder.parts[-4:] if part]
    return MfcSource(
        folder=folder,
        dump_path=dump_path,
        key_path=key_path,
        dump_data=dump_data,
        key_data=key_data,
        uid=uid,
        sha256=digest,
        label=" / ".join(label_parts),
    )

