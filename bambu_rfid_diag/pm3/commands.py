from __future__ import annotations

import re
from collections.abc import Iterable

from ..i18n import Translator, normalize_locale
from ..domain import CommandResult
from .errors import UnsafeCommandError
from .session import ProxmarkRunner


STAGED_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")


def staged_name(value: str, locale: str = "en") -> str:
    """Validate a filename staged inside the trusted PM3 client directory."""
    if not STAGED_NAME_RE.fullmatch(value) or "/" in value or "\\" in value:
        raise UnsafeCommandError(
            Translator(normalize_locale(locale)).t(
                "proxmark.unsafe_staged_name"
            )
        )
    return value


def mfu_page(page: int, locale: str = "en", *, max_page: int = 127) -> int:
    """Validate one writable Type 2 user page against a confirmed profile."""
    max_page = int(max_page)
    if not 4 <= page <= max_page <= 225:
        raise UnsafeCommandError(
            Translator(normalize_locale(locale)).t(
                "proxmark.ntag_page_range_dynamic", max_page=max_page
            )
        )
    return page


def validated_pages(
    pages: Iterable[tuple[int, bytes]],
    locale: str,
    *,
    max_page: int = 127,
) -> list[tuple[int, bytes]]:
    """Validate a bounded, duplicate-free batch of four-byte Type 2 pages."""
    result = list(pages)
    tr = Translator(normalize_locale(locale))
    if not result:
        raise UnsafeCommandError(tr.t("proxmark.ntag_empty_batch"))
    if len(result) > max_page - 3:
        raise UnsafeCommandError(tr.t("proxmark.ntag_batch_too_large"))
    seen: set[int] = set()
    for page, data in result:
        mfu_page(page, locale, max_page=max_page)
        if page in seen:
            raise UnsafeCommandError(
                tr.t("proxmark.ntag_duplicate_page", page=page)
            )
        seen.add(page)
        if len(data) != 4:
            raise UnsafeCommandError(tr.t("proxmark.ntag_page_size"))
    return result


class ProxmarkWriteRunner(ProxmarkRunner):
    """Expose only typed destructive commands with validated arguments."""

    def restore_mfc(
        self,
        dump_name: str,
        key_name: str,
        *,
        use_keyfile_for_auth: bool = False,
    ) -> CommandResult:
        dump_name = staged_name(dump_name, self.locale)
        key_name = staged_name(key_name, self.locale)
        auth = " --ka" if use_keyfile_for_auth else ""
        return self._execute(
            f"hf mf restore --1k --force{auth} -f {dump_name} -k {key_name}"
        )

    def dump_mfc(self, key_name: str, output_name: str) -> CommandResult:
        key_name = staged_name(key_name, self.locale)
        output_name = staged_name(output_name, self.locale)
        return self._execute(
            f"hf mf dump --1k -k {key_name} -f {output_name}"
        )

    def dump_mfu(self, output_name: str) -> CommandResult:
        output_name = staged_name(output_name, self.locale)
        return self._execute(f"hf mfu dump -f {output_name}")

    def restore_mfu(self, dump_name: str) -> CommandResult:
        dump_name = staged_name(dump_name, self.locale)
        return self._execute(f"hf mfu restore -f {dump_name}")

    def write_mfu_page(
        self, page: int, data: bytes, *, max_page: int = 127
    ) -> CommandResult:
        return self.write_mfu_pages([(page, data)], max_page=max_page)

    def write_mfu_pages(
        self,
        pages: list[tuple[int, bytes]],
        *,
        max_page: int = 127,
    ) -> CommandResult:
        pages = validated_pages(pages, self.locale, max_page=max_page)
        command = "; ".join(
            f"hf mfu wrbl -b {page} -d {data.hex().upper()}"
            for page, data in pages
        )
        return self._execute(command)

    def write_mfu_pages_raw(
        self,
        pages: list[tuple[int, bytes]],
        *,
        max_page: int = 127,
    ) -> CommandResult:
        pages = validated_pages(pages, self.locale, max_page=max_page)
        commands: list[str] = []
        last = len(pages) - 1
        for index, (page, data) in enumerate(pages):
            frame = f"A2{page:02X}{data.hex().upper()}"
            select = " -s" if index == 0 else ""
            keep = " -k" if index != last else ""
            commands.append(f"hf 14a raw{select} -c{keep} {frame}")
        return self._execute("; ".join(commands))
