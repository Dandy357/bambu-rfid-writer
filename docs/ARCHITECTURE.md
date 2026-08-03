# Architecture

## Purpose

Bambu RFID Writer is a Tkinter desktop application that executes controlled Proxmark3 workflows for two distinct protocols:

- Bambu MIFARE Classic 1K cloning to compatible writable targets.
- NFC Type 2 NDEF write and erase operations for explicitly supported memory layouts.

The code is organized so protocol rules, PM3 process handling, presentation, and filesystem concerns can be reviewed independently. Compatibility facades preserve the import paths used by v0.5 tests and external scripts.

## Dependency direction

The intended direction is:

```text
UI -> application facades -> workflows -> domain + protocol adapters
                                    -> infrastructure
presentation <- domain reports
```

Lower layers do not import Tkinter. Domain models do not know about translated labels or filesystem paths.

## Package map

### `bambu_rfid_diag/domain`

Stable data structures and identifiers:

- `checks.py`: check states, blocking semantics, and overall result states.
- `commands.py`: immutable PM3 command result.
- `diagnostic_reports.py`: read-only diagnostic report.
- `read_results.py`: decoded read-only NDEF result.
- `write_reports.py`: destructive-operation report.
- `hardware.py`: client, firmware, and hardware information.
- `tags.py`: protocol-neutral tag information.
- `operations.py`: stable operation identifiers used for reporting and filenames.
- `operation_events.py`: stable workflow event names and typed Tkinter queue events.
- `errors.py`: invariant and workflow errors.

Domain objects contain technical state. User-facing text is added by presentation or workflow boundaries through the translator.

### `bambu_rfid_diag/pm3`

The Proxmark3 adapter is split by responsibility:

- `bundle.py`: validate the RRG/Iceman installation and port input.
- `session.py`: own one long-running PM3 process, marker protocol, timeout handling, cancellation, and streamed lines.
- `commands.py`: construct and validate typed destructive commands.
- `protocol.py`: marker parsing, output decoding, and transport-level status inference.
- `results.py`: command-specific semantic completion checks for writes, restores, and dumps.
- `errors.py`: PM3-specific exceptions.

`bambu_rfid_diag/proxmark.py` is a compatibility facade. New code should import from `bambu_rfid_diag.pm3`.

### `bambu_rfid_diag/pm3_parsing`

Pure text parsers grouped by protocol:

- `hardware.py`
- `iso14443a.py`
- `mifare_classic.py`
- `type2.py`
- `text.py`

Parsers do not start processes or write files. `parsers.py` preserves the previous flat imports.

### `bambu_rfid_diag/nfc_type2`

NFC Type 2 data handling without PM3 process logic:

- `models.py`: fields, TLV records, dump models.
- `builder.py`: build URI/text NDEF records and Type 2 TLV images.
- `records.py`: decode NDEF records.
- `tlv.py`: parse and safely clear TLV structures.
- `dump.py`: read PM3 MFU binary dump format.

`ndef.py` is a compatibility facade. The canonical terms are `Type2Field` and `build_type2_ndef`; legacy NTAG names are aliases only.

### `bambu_rfid_diag/workflows`

One orchestrator per destructive operation:

- `mfc_clone.py`: Bambu MIFARE Classic source validation, target classification, backup, restore, and verification.
- `type2_write.py`: Type 2 profile validation, baseline planning, NDEF transaction, and verification.
- `type2_erase.py`: safe in-place NDEF clear or known-profile user-memory zero.
- `preflight_mifare.py`: MIFARE-specific preflight checks.
- `preflight_type2.py`: Type 2 lock, authentication, profile, and originality checks.
- `common.py`: operation lifecycle, event emission, firmware cache, bounded page writes, and shared report finalization.

The public `WriterService` in `writer.py` is intentionally thin. It creates dependencies and selects a workflow.

### `bambu_rfid_diag/diagnostic`

Protocol-specific read-only inspectors:

- `mifare.py`
- `type2.py`

`diagnostics.py` owns the common connection/report lifecycle, enforces the selected CUID or NDEF target family, and delegates protocol interpretation. `ndef_reader.py` owns the separate read-only full-memory NDEF decode operation.

### `bambu_rfid_diag/infrastructure`

Filesystem and persistence adapters:

- `paths.py`: application data paths.
- `settings.py`: validated loading and atomic saving of the string settings map.
- `material_library_cache.py`: atomic persistence of the last material-library snapshot.
- `workspace.py`: unique temporary PM3 filenames and cleanup.

### `bambu_rfid_diag/presentation`

Report rendering and persistence:

- `diagnostic_report.py`
- `write_report.py`
- `ndef_read.py`

Renderers consume stable domain identifiers. They must not infer operation type from translated text.

### `bambu_rfid_diag/ui`

Tkinter components separated by user-facing responsibility:

- `mifare_view.py`: Bambu MIFARE source/library screen.
- `type2_view.py`: NFC Type 2 write/erase screen.
- `type2_editor.py`: dynamic NDEF field editor.
- `material_library.py`: tree population, in-memory restoration, locale refresh, and persistent-cache restoration.
- `option_state.py`: convert persisted settings to immutable workflow options.
- `settings_view.py`: embedded Settings page, connection/library configuration, profile controls, and About information.
- `operations.py`: worker threads, typed UI queue events, cancellation, targeted diagnostics, NDEF reading, and dispatch.
- `callbacks.py`: ownership, debouncing, and cancellation of delayed Tk callbacks.
- `results.py`: live checks, live PM3 output, and final report display.
- `widgets.py`: reusable scrolling widgets and cross-platform mouse-wheel routing.
- `theme.py`: palette tokens, ttk styles, icon repository, inputs, checkboxes, tree colors, and logs.
- `components/mode_switcher.py`: compact Settings, CUID, and Type 2 primary navigation.
- `components/activity_bar.py`: animated operation state panel.
- `components/dialogs.py`: themed modal information, confirmation, warning, error, and copyable text dialogs.
- `constants.py`: stable UI state identifiers.

`app.py` builds the application shell, owns the active appearance, and composes these components. It should not acquire new protocol logic or local color definitions. See `UI_THEMES.md` for the visual-system contract.

## Compatibility policy

The refactor intentionally preserves:

- `models.py`, `parsers.py`, `proxmark.py`, `ndef.py`, and `reporting.py` as facades.
- `NtagWriteOptions`, `NtagEraseOptions`, and old profile function names as exact aliases.
- persisted JSON keys beginning with `ntag_`.
- the stored UI mode value `"ntag"`.
- `WriterService.write_ntag()` and `erase_ntag()` aliases.

New code should use Type 2 terminology. Compatibility names should not be removed until a separately announced breaking release.

## Safety boundaries

The following rules are architectural invariants:

1. One operation owns one PM3 client process.
2. Command completion is established by a unique following marker, not an idle prompt.
3. Destructive commands are built by typed helpers and bounded by the PM3 pipe-safe line length.
4. Unknown Type 2 memory layouts are read-only.
5. Existing valuable data is read and, when configured, persisted before any destructive write.
6. Reports preserve partial commands and output after failure, timeout, or cancellation.
7. Translated text never controls operation selection or report filenames.
8. A warning is not blocking unless the `blocking` flag explicitly says so.

## Adding a feature

- Add protocol facts to a pure model/parser first.
- Add PM3 syntax to a typed command helper.
- Add the operation sequence to the relevant workflow.
- Emit domain checks and stable event names.
- Render text through locale keys at the boundary.
- Add characterization and failure-path tests before changing GUI controls.
- Update the physical validation matrix when hardware behavior is confirmed.
