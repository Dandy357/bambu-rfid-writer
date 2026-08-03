# UI themes and visual components

## Purpose

The interface uses one centralized visual system. Screens must not embed their own background, text, status, or accent colors. This prevents a partial dark mode where fields, checkboxes, lists, or dialogs remain in the native light Windows style.

The active appearance is stored under `appearance` in the application settings. The supported stable identifiers are `light` and `dark`.

## Theme ownership

`bambu_rfid_diag/ui/theme.py` owns:

- palette tokens;
- ttk style definitions;
- input and combobox colors;
- checkbox image elements;
- notebook, tree, and scrollbar styling;
- diagnostic state colors;
- icon lookup and retention.

Screens receive the shared `ThemeManager` from `WriterApp`. New code must consume palette tokens or named styles instead of hard-coding colors.

## Core palette

| Token | Light | Dark | Purpose |
|---|---|---|---|
| `window` | `#F4F7FB` | `#0B1220` | application background |
| `surface` | `#FFFFFF` | `#111827` | cards and table surfaces |
| `surface_alt` | `#EEF3F8` | `#172033` | secondary controls |
| `field` | `#F8FAFC` | `#141E2E` | editable controls |
| `text` | `#172033` | `#E7EEF8` | primary text |
| `text_muted` | `#5B667A` | `#A7B1C2` | descriptions and inactive text |
| `border` | `#C7D2E0` | `#344258` | normal borders |
| `selection` | `#DCE7FF` | `#263B68` | selected rows and text |
| `cuid` | `#4338CA` | `#4F46E5` | CUID/MIFARE actions |
| `type2` | `#0F766E` | `#0F766E` | NFC Type 2/NDEF actions |
| `danger` | `#B42318` | `#BE123C` | destructive user-memory zero |

The palette also defines hover, disabled, warning-card, success-card, progress-track, and log colors. Automated contrast tests require at least 4.5:1 for normal button and diagnostic text and at least 7:1 for primary text against the main field surfaces.

## Diagnostic colors

Diagnostic text requires separate values for each appearance because a color that works on white may disappear on a dark selected row.

| State | Light | Dark |
|---|---|---|
| OK | `#166534` | `#86EFAC` |
| Warning | `#92400E` | `#FCD34D` |
| Error | `#B91C1C` | `#FDA4AF` |
| Information | `#1D4ED8` | `#93C5FD` |
| Skipped | `#64748B` | `#CBD5E1` |

Every row also has an icon and a localized state label. Color is supplementary, not the only carrier of meaning. When a row is selected, selection contrast takes priority over retaining the original text color.

## Inputs and checkboxes

`TEntry` and `TCombobox` explicitly define:

- normal, hover, focus, readonly, disabled, and invalid states;
- field background and text;
- cursor and selection colors;
- border and arrow colors;
- combobox popup list colors.

Checkboxes use packaged images for checked, unchecked, checked-disabled, and unchecked-disabled states. The control remains a real `ttk.Checkbutton` with keyboard focus and a normal Tk variable.

## Icons

Icons are stored under `bambu_rfid_diag/assets/icons` and loaded through `IconRepository`. Variants include light, dark, muted, inverse, status, and checkbox assets. Sizes are prepared in advance rather than scaled by Tk at runtime.

`tools/generate_icons.py` recreates the complete asset set. The generated images are distributable application resources; source code must retain the Tk image objects through the repository cache.

## Major components

- `ModeSwitcher`: compact primary navigation with a square Settings control and distinct CUID and Type 2 accents.
- `ActivityBar`: card-based status panel with an animated rounded segment and idle/running/cancelling/success/error states.
- `ThemedDialogs`: modal information, warning, error, and confirmation dialogs that follow the active appearance.
- `OperationResultsMixin`: themed diagnostic tree and line-level PM3 prefix highlighting.

## Theme switching

Switching appearance rebuilds the widget tree because several native ttk elements cannot be reliably recolored in place on every Tk build. The application preserves:

- all Tk variables and entered values;
- selected CUID/Type 2 mode;
- selected result/protocol tabs;
- reports and report paths;
- current settings values.

Theme switching is disabled while an operation is running.

## Rules for future changes

1. Do not introduce raw color literals outside `ui/theme.py` or the icon generator.
2. Add a named style when a component has a new semantic role.
3. Verify normal, focus, hover, readonly, disabled, and selected states.
4. Check both appearances with a real editable field and a populated tree.
5. Do not communicate a safety state only through color.
6. Keep saved reports free of GUI-only color markup.
7. Add new icons to the generator rather than embedding base64 or depending on Unicode glyph availability.
