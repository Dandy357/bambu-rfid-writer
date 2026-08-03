from __future__ import annotations

import threading
from pathlib import Path

from .domain import NdefReadResult
from .i18n import Translator, normalize_locale
from .infrastructure.workspace import OperationWorkspace
from .nfc_type2 import parse_mfu_dump, parse_ndef_message
from .options import TimeoutOptions
from .pm3 import ProxmarkWriteRunner, resolve_bundle, validate_port
from .pm3.results import mfu_dump_succeeded
from .pm3_parsing import enrich_mfu_info, parse_iso14a
from .workflows.common import read_exact_output


class NdefReadService:
    """Read and decode one NFC Forum Type 2 NDEF message without writing."""

    def __init__(
        self,
        *,
        locale: str = "en",
        timeouts: TimeoutOptions | None = None,
        cancel_event: threading.Event | None = None,
        on_event=None,
    ) -> None:
        self.locale = normalize_locale(locale)
        self.t = Translator(self.locale).t
        self.timeouts = (timeouts or TimeoutOptions()).normalized()
        self.cancel_event = cancel_event
        self.on_event = on_event

    def read(
        self,
        bundle_root: str | Path,
        port: str | None = None,
        *,
        on_progress=None,
    ) -> NdefReadResult:
        progress = on_progress or (lambda _message: None)
        layout = resolve_bundle(bundle_root, self.locale)
        requested_port = validate_port(port, self.locale)
        runner = ProxmarkWriteRunner(
            layout,
            requested_port,
            locale=self.locale,
            timeouts=self.timeouts,
            cancel_event=self.cancel_event,
            on_event=self.on_event,
        )
        workspace = OperationWorkspace(layout.client_dir)
        output_path = workspace.reserve("ndef_read", "ndef_read.bin")
        try:
            progress(self.t("reader.connect_progress"))
            runner.open()
            identity = runner.run("hw version; hf 14a info")
            tag = parse_iso14a(identity.output, self.locale)
            if identity.timed_out:
                raise RuntimeError(self.t("reader.identity_failed"))
            if not tag.present:
                raise ValueError(self.t("reader.no_tag"))
            if identity.returncode != 0:
                raise RuntimeError(self.t("reader.identity_failed"))
            if tag.family == "mfc1k":
                raise ValueError(self.t("reader.wrong_tag_type", actual=tag.display_type))

            progress(self.t("reader.inspect_progress"))
            type_info = runner.run("hf mfu info")
            if type_info.timed_out or type_info.returncode != 0:
                raise RuntimeError(self.t("reader.type2_info_failed"))
            enrich_mfu_info(tag, type_info.output, self.locale)
            if tag.family not in {"type2", "ntag213", "ntag215", "ntag216"}:
                raise ValueError(self.t("reader.wrong_tag_type", actual=tag.display_type))

            progress(self.t("reader.dump_progress"))
            dump_result = runner.dump_mfu(workspace.names["ndef_read"])
            if not mfu_dump_succeeded(dump_result, output_path):
                raise RuntimeError(self.t("reader.dump_failed"))
            parsed = parse_mfu_dump(read_exact_output(output_path, self.locale), self.locale)
            records = (
                tuple(parse_ndef_message(parsed.ndef_message, self.locale))
                if parsed.ndef_message is not None
                else ()
            )
            profile_name = (
                parsed.profile.display_name
                if parsed.profile is not None
                else tag.display_type
            )
            return NdefReadResult(
                uid=parsed.uid.hex(" ").upper(),
                profile_name=profile_name,
                records=records,
                message_bytes=parsed.ndef_message,
            )
        finally:
            runner.close()
            workspace.cleanup()
