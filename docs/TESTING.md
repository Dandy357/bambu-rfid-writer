# Testing

## Standard tests

From the project root:

```text
python -m unittest discover -s tests -q
```

The tests cover parsers, source validation, workflow decisions, command construction, reports, targeted diagnostics, read-only NDEF decoding, localized automatic COM detection, compatibility aliases, settings persistence, and marker-stream behavior. Simulated tests cannot prove RF behavior or clone-specific silicon behavior.

## Locale validation

```text
python tools/check_locales.py
```

This requires Czech and English to have identical keys and identical format placeholders.

## Source quality validation

```text
python tools/check_source_quality.py
```

This checks:

- production and helper modules parse;
- production/helper lines do not exceed 100 characters;
- non-facade production modules contain no unused imports;
- production code contains no runtime `assert` statements;
- developer comments and docstrings use English ASCII text;
- UI hexadecimal colors are centralized in `ui/theme.py`.

User-facing localized strings are intentionally stored outside this check.

## Icon asset validation

```text
python tools/check_icon_assets.py
```

This verifies the complete expected set of 186 packaged PNG icons, status symbols, and checkbox states without requiring Pillow at runtime.

## GUI smoke test

```text
python tools/gui_smoke_test.py
```

Run this on Windows with a desktop session. On Linux CI, wrap it in `xvfb-run -a`. It opens the main window, verifies compact Settings/CUID/NDEF navigation and the embedded Settings page, checks both appearances, themed entries, trees and checkbox layouts, resizes and persists the material-library divider, preserves form values and the material library across theme and language rebuilds, verifies main-window mouse-wheel routing and persistent library-cache restoration, exercises the activity panel and themed dialogs, verifies the protocol-specific check and NDEF-read controls, processes a typed queue event, and closes without leaving a scheduled Tk callback.

## Coverage

```text
python -m pytest --cov=bambu_rfid_diag --cov-report=term-missing
```

GUI modules are exercised by the smoke test rather than line-oriented unit coverage. Coverage percentages must therefore be reported with that limitation instead of treating unimported Tkinter modules as proven.

## Clean-package verification

Before distributing a ZIP:

1. remove `__pycache__`, `.pyc`, `.pytest_cache`, coverage files, and build output;
2. create the ZIP;
3. extract it into a new directory;
4. compile all modules;
5. run unit, locale, and source-quality checks;
6. run the GUI smoke test;
7. record the ZIP SHA-256;
8. state separately which hardware scenarios were physically confirmed.
