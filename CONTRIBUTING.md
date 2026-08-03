# Contributing

Thank you for helping improve Bambu RFID Writer.

## Before opening an issue

- Confirm that the problem is reproducible with the latest public release.
- Include the application version, Windows version, Proxmark3 client build, tag family, and operation profile.
- Remove personal paths, real tag dumps, keys, UIDs, purchase information, and unrelated log content.
- Never upload data from a tag that you do not own or have permission to inspect.

## Pull requests

1. Keep protocol-specific safety checks intact.
2. Run `Run_Tests.bat` and `Run_Quality_Checks.bat` where possible.
3. Add or update tests for changed behavior.
4. Mark hardware behavior as physically confirmed only when it was tested on real hardware.
5. Do not add destructive support for an unverified tag family or memory layout.
6. Do not commit generated caches, local settings, logs, backups, real dumps, or key files.

AI-assisted contributions are welcome, but the contributor remains responsible for reviewing, understanding, testing, and accurately describing the submitted change.

## Language files

English is the source/default interface language. Czech remains an optional translation. Keep locale keys aligned and follow `bambu_rfid_diag/locales/ADDING_LANGUAGES.md` when adding another language.
