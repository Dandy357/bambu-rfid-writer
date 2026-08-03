# Technical audit — Bambu RFID Writer 0.8.0

## 1. Release decision

The application is close to a 1.0.0 release, but 0.8.0 remains the appropriate version
number until the final Windows EXE and selected hardware scenarios are physically
confirmed. The codebase is structurally suitable for a stable release after those checks;
no further broad refactor is recommended.

## 2. Architecture result

Responsibilities are separated into domain, PM3 adapter, parsers, protocol workflows,
infrastructure, presentation, and Tkinter UI. The public `WriterService` remains a thin
facade. Destructive sequence ownership remains protocol-specific:

- `workflows/mfc_clone.py`;
- `workflows/type2_write.py`;
- `workflows/type2_erase.py`.

The larger workflow files are linear protocol descriptions with named private phases.
Splitting them further would currently increase cross-file navigation without a clear
correctness benefit.

## 3. Correctness fixes from the deep audit

### Semantic PM3 results

The old generic rule could treat empty or non-confirming output as success when the
transport itself completed. Version 0.8.0 adds typed validators in `pm3/results.py` and
uses them at every destructive workflow boundary. A zero process return code is no
longer enough for page writes, restore, or dump operations.

### Programmed CUID

The previous experimental same-data block-0 probe was removed from the stable workflow.
The supported behavior is now explicit:

1. locate current keys by target UID;
2. read the complete target;
3. persist a backup when enabled;
4. return **No change** on a 1024/1024 match;
5. block different programmed content as unsupported before any destructive command.

The low-level unused block read/write helpers and their stale error strings were removed.
The typed `restore --ka` capability may remain in the PM3 adapter for future documented
work, but the stable UI workflow does not reach it for a different programmed target.

### Settings and profiles

Settings-save errors are visible, logged, and return a failure status. Closing or starting
an operation does not silently continue after a failed required save. Persisted options
are compared with named profile presets; mismatched combinations are represented as
**Custom**. String booleans are parsed strictly.

### Repeated lifecycle

All delayed Tk callbacks are owned by `CallbackRegistry`. UI rebuild and application
shutdown cancel them before destroying widgets. A first application window can be
destroyed and a second created in the same process without stale callback errors.
`ProxmarkRunner` is explicitly one-shot and its close path is idempotent.

### Cache correctness

The firmware-result cache includes a fingerprint of the selected PM3 installation files,
so changing the client invalidates the cached success. Material-library cache paths are
resolved below the configured root and reject absolute or parent-traversal paths.

### CUID scrolling

The CUID work page again owns a vertical scroll container. Nested scrolling is directional:
the material tree consumes the wheel while it can move, then hands the event to the outer
page at its boundary.

## 4. Dead-code and syntax audit

Removed during the audit:

- an unused workflow exception;
- prompt-era completion helpers superseded by marker synchronization;
- an obsolete Settings-dialog compatibility implementation;
- an unused MIFARE block parser;
- unused Type 2/MIFARE model properties;
- an unused callback-registry method;
- an unused skipped-check helper;
- unused MIFARE block/info command methods;
- stale translation entries associated with the removed block-0 probe;
- unused imports found by static analysis.

The source-quality tool now checks production and helper code for:

- valid Python syntax;
- maximum 100-character lines;
- English ASCII developer comments/docstrings;
- unused imports outside intentional facade modules;
- absence of runtime `assert`;
- absence of local hexadecimal UI colors outside `ui/theme.py`.

Ruff configuration mirrors the core style/import checks for contributors, but Ruff is not
a runtime dependency.

## 5. Compatibility policy

The following flat modules remain intentional public compatibility facades:

- `models.py`;
- `parsers.py`;
- `proxmark.py`;
- `ndef.py`;
- `reporting.py`.

New internal code imports canonical packages directly. Legacy `ntag_*` settings keys and
old Type 2 aliases remain to preserve existing user settings and external scripts.

## 6. Testing and coverage

The working-tree result before final packaging is 116 unit tests and 45 parameterized
subtests. GUI behavior is tested separately under Xvfb, including both themes, embedded
Settings, cache restoration, CUID scrolling, repeated rebuilds, and complete window
recreation.

Line/branch coverage from ordinary pytest is approximately 53% because most Tkinter code
is intentionally exercised by the separate GUI smoke process rather than imported into
the coverage run. Core workflow and parser modules are generally in the 70–90% range.
Coverage is not hardware evidence.

## 7. Remaining release risks

The following are not code-quality failures but still require physical confirmation before
calling the same code 1.0.0:

- build and launch the real Windows EXE;
- repeat a fresh-CUID first write with the stabilized package;
- verify the exact-match programmed-CUID no-change path on hardware;
- repeat NTAG215 write, NDEF clear, and full zero;
- verify cancellation during a real long PM3 operation;
- optionally test Windows DPI 125%, 150%, and 200%;
- test NTAG213/216 only on disposable tags.

A different-content programmed-CUID rewrite should not be included in the 1.0 acceptance
criteria because it is intentionally unsupported until a documented, physically verified
chip-specific mechanism is available.
