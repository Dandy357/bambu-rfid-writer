# Adding another language

GUI, diagnostic, validation and report translations are stored in separate JSON catalogs.
A language can be added without changing the write logic:

1. Copy `en.json` to `<language-code>.json`, for example `de.json`.
2. Keep every existing key and translate values only.
3. Set `language.name` to the language name shown in Settings.
4. Add translations for every new key introduced by future features.
5. Run `Run_Tests.bat`. All catalogs must contain the same key set.

`Build_EXE.bat` automatically includes all files from `bambu_rfid_diag/locales` in the Windows executable.
