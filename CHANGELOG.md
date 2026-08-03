# Changelog

## 0.9.3 — 2026-08-03

- Replaced the provisional low-fidelity icon set with a new consistent asset pack for light, dark, inverse, and muted variants.
- Redrew the primary action and navigation symbols with cleaner geometry, blue accent details, and improved small-size legibility.
- Reworked the status icons (`ok`, `warning`, `error`, `info`, `skip`) to match the refreshed visual language.
- Added a new application icon and regenerated the packaged PNG/ICO outputs from the new source asset.
- Rebuilt icon-generation assets and revalidated the icon inventory, source-quality checks, and automated tests.

All notable changes to Bambu RFID Writer are documented here.

## 0.9.2 — 2026-08-03

- Added explicit **Check CUID** and **Check NDEF** actions to the corresponding protocol pages.
- Made protocol diagnostics target-specific: a CUID check no longer falls through to Type 2 inspection, and an NDEF check no longer runs MIFARE Classic key checks.
- Added a read-only **Read NDEF** operation that creates a temporary MFU dump, decodes supported Text and URI records, displays them in a copyable scrollable dialog, and removes the temporary files.
- Added readable fallback output for unsupported NDEF records without attempting to interpret their payload.
- Fixed automatic COM detection when the localized combobox value is stored or validated, including after a language change.
- Updated the COM validation message to describe the `COM(X)` form and automatic detection explicitly.
- Expanded diagnostic, NDEF-reader, COM-validation, and GUI contract tests.

All notable changes to Bambu RFID Writer are documented here.

## 0.9.1 — 2026-08-03

- Moved `language.name` to the first entry in every locale catalog while keeping the remaining keys alphabetically ordered.
- Renamed the first Settings notebook tab to **General**.
- Added a destructive **Delete user data** action in General settings. It removes settings, the material-library cache, logs, and backups, then exits without recreating the deleted files.
- Added a second confirmation step before deleting all per-user data.
- Made **Clear NDEF content** the larger normal erase action and **Zero user memory** a smaller red destructive action.
- Added a dedicated validation message for an incomplete `https://` or `http://` value.
- Added automatically hidden horizontal scrollbars to long NDEF value fields.
- Removed the automatically inserted colon between an enabled field name and its value in encoded NDEF text.
- Expanded unit and GUI regression coverage for all of the above changes.

## 0.9.0 — 2026-08-03

- Changed the clean-install default language from Czech to English.
- Changed default localization parameters in parsers, workflows, reports, and public helper APIs to English.
- Rewrote the public README, quick instructions, release notes, test descriptions, and repository-facing text in English.
- Kept Czech exclusively as an optional translation catalog in `bambu_rfid_diag/locales/cs.json`.
- Replaced the real MFU test sample with a synthetic fixture containing no real UID, product identifier, URL, or purchase data.
- Rebuilt the NDEF field editor around one ordered field list.
- Added removal controls for built-in fields as well as custom fields.
- Added move-up and move-down controls for every NDEF field.
- Added separate controls for creating text fields and the optional URI field.
- Added support for text-only and URI-only NDEF messages.
- Preserved the exact displayed order by grouping consecutive text fields into text records around the URI record.
- Added persistence of the complete ordered NDEF field list and automatic migration from the legacy fixed-field settings used by 0.8.3 and earlier.
- Added validation that permits zero or one URI field and rejects multiple URI fields.
- Updated automated tests for exact NDEF record ordering and the new English defaults.

## 0.8.3 — 2026-08-03

- Fixed a CUID scrolling regression in which the previously allocated paned-window height could remain part of the logical scrollable area.
- The CUID scroll region now returns to the actual content height after a large-window to small-window resize cycle.
- Prevented child requested-size changes caused by scrollbar visibility from pushing the native top-level window geometry during edge dragging.
- Added regression coverage for shrinking the main window after it had been enlarged.

## 0.8.2 — 2026-08-03

- Added automatically hidden vertical and horizontal scrollbars throughout the main pages, material library, NDEF editor, results, and raw log.
- Scrollbars now appear only when content exceeds the available area and disappear again when the area becomes large enough.
- Added resize regression tests for both visibility directions.

## 0.8.1 — 2026-08-03

- Fixed CUID page height recalculation while dragging the divider between the material library and write controls.
- The outer scrolling page now follows both increases and decreases in the real required content height.
- Moved **Save** and **Cancel operation** into the same footer row.
- Added GUI contract tests for the divider and footer layout.

## 0.8.0 — 2026-08-03

- Completed a broad source audit and modular refactor.
- Split diagnostic, workflow, presentation, PM3, NFC Type 2, settings, and UI responsibilities into smaller modules while retaining compatibility facades.
- Removed unused code and tightened public contracts.
- Added source-quality, icon, locale, syntax, and GUI smoke checks.
- Improved resize performance by managing only the active primary page and debouncing layout work.
- Replaced the settings dialog with a full Settings page and compact top navigation.
- Added light and dark visual systems, state icons, and an animated activity bar.

## 0.7.x — 2026-08-03

- Improved mode navigation, settings organization, material-library management, and responsive layout behavior.
- Added theme-aware controls, reports, status indicators, dialogs, and application icon assets.
- Expanded GUI smoke coverage for both themes and minimum window sizes.

## 0.6.x — 2026-08-03

- Continued the architectural refactor into domain, infrastructure, workflow, presentation, and UI layers.
- Added compatibility modules so older imports continued to work during the transition.
- Expanded tests for settings persistence, PM3 results, workflow safety, and rendering contracts.

## 0.5.0 — 2026-08-02

- Generalized the former NTAG-only path into NFC Forum Type 2 / NDEF support.
- Added known NTAG213, NTAG215, and NTAG216 profiles with profile-specific capacity, lock, and configuration pages.
- Added a TLV parser and safe NDEF clearing that preserves unrelated TLVs.
- Split erasing into **Clear NDEF content** and **Zero user area**.
- Added writing of changed pages only and cleanup of stale data from a previously longer NDEF message.
- Added a diagnostic-only generic Type 2 profile while keeping unknown layouts blocked for writing.
- Improved CUID handling for factory tags, known programmed tags, current-key lookup, backup, and identical-content detection.
- Added material-library cache validation and richer ready, warning, invalid, and unverified states.
- Added extensive regressions for ECC warnings, profile limits, CUID authentication, duplicate UIDs, TLV preservation, and old-message cleanup.

## 0.4.0.2 — 2026-08-02

- Fixed startup of interactive PM3 operations when redirected stdin did not produce an idle prompt.
- Added harmless startup and completion markers to determine when commands were ready and finished.
- Removed internal markers from the user-visible raw protocol.
- Correctly classified startup timeouts and included captured startup output in failures.

## 0.4.0.1 — 2026-08-02

- Fixed stalled NFC Type 2 writing and erasing in an interactive PM3 session.
- Split page writes into short batches that stay below the PM3 redirected-input buffer limit.
- Kept one PM3 process per operation while waiting for completion between batches.
- Added batch progress and stopped subsequent batches after a failure.

## 0.4.0 — 2026-08-02

- Moved diagnostic and write operations to one long-lived PM3 session per operation.
- Added Fast, Recommended, Thorough, and Custom profiles for CUID, NDEF writing, and erasing.
- Added configurable checks, backups, readbacks, methods, and timeout limits.
- Added fast RAW writing, generated MFU restore, and compatible page-by-page writing.
- Added complete operation cancellation with PM3 process-tree termination.
- Added session counts, timeout reasons, profile names, and method names to reports.

## 0.3.1.3 — 2026-08-02

- Fixed a CUID write regression introduced by fast material-library discovery.
- Kept the UID in a folder name as a discovery hint while treating the UID inside the validated dump as authoritative.
- Reused the exact source object validated by the GUI instead of reopening it immediately before writing.
- Fixed a translation-parameter naming collision that stopped CUID writing before confirmation.

## 0.3.1.2 — 2026-08-02

- Removed automatic full library scanning at startup and during language changes.
- Made library loading an explicit user action.
- Used directory names only during fast discovery and delayed dump/key validation until the write workflow.
- Recognized candidate folders that consist of, or end with, eight hexadecimal characters.
- Added a final folder-name UID comparison during full validation.

## 0.3.1.1 — 2026-08-02

- Added vertical scrolling to CUID and NDEF write pages.
- Added responsive text wrapping.
- Added vertical and horizontal scrolling to diagnostic tables and raw logs.
- Improved minimum-window behavior and long-path wrapping.

## 0.3.1 — 2026-08-02

- Batched NDEF page writes in one PM3 client session.
- Moved the URI row to the first editor position and encoded the URI as the primary record.
- Preserved text-field order in the text record.
- Added batch-write safety errors and progress reporting.

## 0.3.0 — 2026-08-02

- Added the first multi-page GUI with CUID, NDEF, results, diagnostics, and complete logs.
- Added material-library browsing and direct source selection.
- Added optional final verification for CUID and NDEF operations.
- Added complete NDEF user-area clearing with backup and protected-area verification.
- Added custom NDEF fields and optional field-name writing.
- Persisted NDEF values and operation settings.
- Renamed scripts and technical files in English and added English quick instructions.

## 0.2.1 — 2026-08-02

- Reworked messages into a concise, impersonal technical style.
- Removed the separate CUID risk checkbox while retaining the final confirmation dialog.
- Added Czech and English GUI, diagnostic, validation, and report catalogs.
- Persisted the selected language and bundled locale catalogs into the optional executable.

## 0.2.0 — 2026-08-02

- Added the first write-capable GUI with separate CUID and NTAG215 paths.
- Fixed parsing of the real PM3 MIFARE key table format.
- Added offline validation of 1 KiB dumps, 192-byte key files, BCC, keys, and access bits.
- Added mandatory physical preflight diagnostics and complete target backup.
- Added complete CUID restore verification and two-phase NTAG page writing.
- Added protected-memory and `AUTH0` verification.

## 0.1.2 — 2026-08-02

- Released the read-only diagnostic prototype.
- Added detailed `hw version` parsing, Type 2 ECC assessment, MIFARE/CUID classification, and future-write blocking rules.
