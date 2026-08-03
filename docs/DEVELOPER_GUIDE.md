# Developer guide

## Naming

Use these canonical terms in new code:

- `Mfc` for MIFARE Classic.
- `Type2` for NFC Type 2.
- `NDEF` for message/TLV behavior.
- `NTAG213/215/216` only for concrete NXP-compatible profiles.

Old `ntag_*` JSON keys and compatibility aliases are intentional. Do not copy them into new APIs.

## Comments and docstrings

Developer-facing comments and docstrings must be English. Explain constraints and reasons, not a line-by-line restatement of the code. User-facing Czech and English belong in locale catalogs.

## Error handling

- Use explicit exceptions for invalid runtime state; do not use `assert`.
- Catch broad exceptions only at process/workflow/thread boundaries where a partial report must be returned.
- Preserve the traceback in logs or the fatal GUI event.
- Protocol helpers should raise narrow validation errors before sending a command.

## Reports and localization

Use stable operation and check identifiers internally. Translate at the workflow/presentation boundary. Never branch on a translated sentence and never derive a filename from a localized label.

## Compatibility facades

Flat modules such as `writer.py`, `proxmark.py`, `parsers.py`, and `ndef.py` are supported entry points. Their implementation should remain thin. Put new logic in the package named for its responsibility.

## Review checklist

- Is the change in the correct layer?
- Can it be tested without Tkinter or hardware?
- Does a destructive command use a typed helper?
- Does an unknown layout fail closed?
- Is valuable existing data read and persisted before a destructive write?
- Are warning and blocking semantics explicit?
- Are partial outputs retained on failure?
- Are all new comments/docstrings English?
- Do locale keys and placeholders match?
- Is physical validation status stated honestly?
