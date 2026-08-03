# Bambu RFID Writer 0.9.3

<p align="center">
  <img src="bambu_rfid_diag/assets/app_icon_128.png" width="128" alt="Bambu RFID Writer application icon">
</p>

Bambu RFID Writer is a Windows desktop application for controlled Bambu-compatible MIFARE Classic and NFC Forum Type 2 / NDEF workflows through an RRG/Iceman Proxmark3 client.

The application provides a graphical interface for operations that would otherwise require manually prepared Proxmark3 commands, source files, backups, and verification steps.

> **First public beta:** Version 0.9.3 is the first public release. The automated test suite covers parsers, safety rules, command generation, workflows, settings, and core GUI contracts. NTAG215 writing, NDEF reading, and full user-area clearing have been physically confirmed by the maintainer. NTAG213 and NTAG216 destructive operations are implemented but have not yet been physically confirmed. Rewriting an already-programmed CUID with different content is intentionally blocked.

## Download and release status

Download the user package from the repository's **Releases** page. Version 0.9.3 is published as a **pre-release / public beta** rather than a final 1.0 release.

The release package contains the source launcher and can optionally build a Windows executable locally. A compatible RRG/Iceman Proxmark3 package is still required separately.

## Main features

### MIFARE Classic 1K / CUID Gen2 only

- Load Bambu MIFARE Classic 1K dump and key pairs from a material library.
- Write only to a compatible MIFARE Classic 1K Magic Gen2 / CUID Gen2 target.
- Validate dump size, key size, UID, BCC, trailer keys, and access bits.
- Detect a compatible CUID / Magic Gen2 target before writing.
- Verify all 32 default keys on a new target when the selected profile requires it.
- Back up valuable existing target data before a write.
- Restore the complete 1 KiB image and optionally compare it byte for byte.
- Recognize an already-programmed tag with identical content and finish without writing.
- Block unsupported replacement of different content on an already-programmed CUID.

> [!IMPORTANT]
> **CUID support is limited to MIFARE Classic 1K Magic Gen2 / CUID Gen2 tags.**
> Standard non-magic MIFARE Classic tags and other Magic generations, including
> Gen1a, Gen3, and Gen4, are not supported for writing.

### NFC Type 2 / NDEF

- Detect known NTAG213, NTAG215, and NTAG216 memory profiles.
- Validate static lock bits, dynamic lock bits, `AUTH0`, and optional ECC information.
- Write NDEF through fast RAW commands, a generated MFU restore image, or compatible page-by-page commands.
- Clear only the NDEF TLV while preserving other known TLVs.
- Zero the complete user area of a confirmed known profile.
- Write only changed pages and optionally verify the final content.
- Add, remove, and reorder every NDEF editor field, including the original default fields.
- Create text-only, link-only, or mixed NDEF messages.
- Place the clickable URI record at the exact position shown in the editor. Consecutive text fields are compacted into text records around it.
- Persist the complete field list, values, types, and order.
- Read an NFC Type 2 tag without writing and display decoded Text and URI records in a copyable dialog.

### Interface and diagnostics

- English is the default language on a clean installation.
- Czech remains available from the Settings page.
- Light and dark themes.
- Separate CUID, NDEF, and Settings pages.
- Resizable material-library divider.
- Scrollbars appear only when their content overflows.
- Live operation progress and complete Proxmark3 output.
- Separate target-specific CUID and NDEF diagnostics.
- Structured diagnostic and write reports.
- Per-user logs, backups, settings, and material-library cache.
- A General-settings action can delete all application user data and close without recreating it.

## Requirements

- Windows 10 or Windows 11.
- Python 3.10 or newer with Tkinter for the source version.
- An RRG/Iceman Proxmark3 Windows package containing `pm3.bat` and the expected client environment.
- A supported Proxmark3 device and a tag appropriate for the selected operation.

The application does not bundle Proxmark3 firmware, the Proxmark3 client, Bambu material dumps, keys, or tag data.

## Running the source version

1. Extract the complete archive to a new folder.
2. Close other Proxmark3 client windows and processes.
3. Run `Run_Bambu_RFID_Writer.bat`.
4. Open **Settings**.
5. Select the folder containing `pm3.bat`.
6. Select a COM port or leave automatic detection enabled.
7. Select the root of the material library when using CUID workflows.
8. Save the settings and open the required CUID or NDEF page.
9. Use **Check CUID** or **Check NDEF** before a first write to verify the expected tag family.

## Clean-install test

User data is stored outside the program folder:

```text
%LOCALAPPDATA%\BambuRFIDWriter
```

This normally expands to:

```text
C:\Users\<Windows user>\AppData\Local\BambuRFIDWriter
```

The directory may contain:

```text
settings.json
material_library_cache.json
logs\
backups\
```

To test a completely clean installation from the application:

1. Open **Settings → General**.
2. Optionally copy any required backups or logs elsewhere.
3. Press **Delete user data** and accept both confirmation dialogs.
4. The application deletes the complete per-user directory and closes immediately without saving it again.
5. Start the application again.

The same test can be performed manually by closing Bambu RFID Writer and deleting or renaming `%LOCALAPPDATA%\BambuRFIDWriter`.

The next launch will use English and recreate user data as required. Deleting this directory does **not** delete the external Proxmark3 package or the selected material library.

A quick way to open the location is to press `Win + R`, enter:

```text
%LOCALAPPDATA%\BambuRFIDWriter
```

and press Enter.

## Operation profiles

### Fast

Keeps the minimum checks required by the workflow but skips several time-consuming steps such as firmware comparison, backups of empty factory targets, and final readback where configured. It is not recommended for a first attempt with an unknown or valuable tag.

### Recommended

The default balance between safety and speed. It validates the target, protects valuable existing data, and keeps the most useful final verification while avoiding redundant reads.

### Thorough

Enables all available optional checks and intermediate verification steps. A missing, zero, or invalid NXP ECC signature is reported as origin information and does not by itself block compatible clone tags.

### Custom

Allows individual optional checks to be enabled or disabled. Technical conditions required to construct a safe operation remain enforced by the workflow.

## NDEF field editor

Each row represents one logical field. The arrow buttons change its order and **Remove** deletes it, including built-in rows such as Brand, Filament, Purchased, and Link.

- **Add text field** creates a text value.
- **Add link field** creates the optional clickable URI record.
- At most one link field is supported.
- A message may contain no link at all.
- At least one non-empty field is required.
- The **Write field name** option applies only to text fields. When enabled, the name and value are separated by one space; no colon is inserted automatically.
- Long values expose an automatically hidden horizontal scrollbar only when the text exceeds the visible field width.
- The displayed order is the encoded record order.

Settings from version 0.8.3 and earlier are migrated automatically to the new ordered field-list format when first loaded. The larger **Clear NDEF content** action removes only the NDEF TLV; the smaller red **Zero user memory** action clears the complete known user area.

**Read NDEF** performs a read-only tag check and temporary full MFU dump. Supported Text and URI records are decoded in their stored order and shown in a scrollable, copyable window. Unsupported records are listed with their TNF, type, and raw payload. Temporary dump files are deleted when the operation finishes.

## Material-library discovery

A tag candidate is a folder whose name consists of, or ends with, eight hexadecimal characters. Discovery is intentionally fast and does not fully open every dump during the initial tree scan. Full source validation runs before a CUID operation.

The folder selected for writing must resolve to one unambiguous dump and key pair. The UID inside the validated dump is authoritative; the folder name is only a discovery hint.

## Safety boundaries

- Writing is restricted to explicitly supported workflows.
- User-supplied paths and generated PM3 commands are validated before execution.
- NFC Type 2 writes are restricted to the confirmed user-memory range of the detected profile.
- UID, lock, and configuration pages are not treated as ordinary NDEF user pages.
- Unsupported tag layouts remain read-only.
- The dedicated CUID and NDEF checks stop on the wrong protocol family instead of switching to another diagnostic automatically.
- Cancellation terminates the active PM3 process tree.
- A failed or cancelled operation must be checked against the saved report and backup before another write is attempted.

Use the application only with tags and data that you own or are authorized to use.

## Building the optional executable

Run:

```text
Build_EXE.bat
```

The script creates a local `.build-tools` environment, installs a compatible PyInstaller release, and builds through `Bambu_RFID_Writer.spec`. The expected output is:

```text
dist\Bambu_RFID_Writer.exe
```

The executable still requires a separately installed or extracted Proxmark3 Windows package.

## Tests and quality checks

Run the full automated test suite:

```text
Run_Tests.bat
```

Run the broader source, locale, icon, syntax, and GUI checks:

```text
Run_Quality_Checks.bat
```

Technical documentation is available in `docs/`:

- `ARCHITECTURE.md`
- `DEVELOPER_GUIDE.md`
- `PM3_PROTOCOL.md`
- `TAG_SUPPORT.md`
- `TESTING.md`
- `UI_THEMES.md`

## Development and AI assistance

Bambu RFID Writer was designed, specified, iteratively reviewed, and physically tested by Daniel Blažek. Most source code and documentation were generated and revised with substantial assistance from ChatGPT. Released versions are selected and tested by the maintainer, who remains responsible for project decisions, release notes, and issue handling.

## Independence and trademarks

This project is not affiliated with, endorsed by, or supported by Bambu Lab or the Proxmark3 project. Product and project names belong to their respective owners.

## Contributing and security

See `CONTRIBUTING.md` before opening a pull request or submitting hardware results. Do not upload real dumps, keys, UIDs, backups, personal paths, or private log content. Potentially sensitive write-safety problems should be handled according to `SECURITY.md`.

## License

Bambu RFID Writer is released under the MIT License. See `LICENSE`. The license applies to this repository and its original assets; it does not grant rights to Proxmark3, Bambu Lab products, third-party material libraries, tag data, or external dependencies.
