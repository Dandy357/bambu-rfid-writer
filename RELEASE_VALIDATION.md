# Release validation — 0.9.3 Public Beta

Date: 2026-08-03

## Release scope

Version 0.9.3 is the first public beta release of Bambu RFID Writer. It includes the complete 0.9 feature line and replaces the provisional interface graphics with a regenerated icon system for light, dark, inverse, muted, and status variants.

The main public workflows are:

- target-specific **Check CUID** diagnostics;
- first-write CUID / Magic Gen2 restoration with optional backup and verification;
- target-specific **Check NDEF** diagnostics;
- read-only **Read NDEF** with decoded Text and URI records in a copyable dialog;
- ordered NDEF construction and writing for known NFC Type 2 profiles;
- **Clear NDEF content** without intentionally clearing the complete known user area;
- the separate destructive **Zero user memory** action;
- English-first clean installation with an optional Czech translation;
- local user-data deletion and clean-install testing.

## Public-repository preparation

Before creating the public packages:

- the MIT license was added;
- contribution, security, pull-request, bug-report, and hardware-test templates were added;
- Python caches, pytest caches, local build output, and compiled bytecode were removed;
- real-world identifiers remaining in test examples were replaced with clearly synthetic UIDs;
- the MFU binary fixture remained synthetic and contains only example data;
- `.gitignore` was expanded to exclude user settings, logs, backups, dumps, keys, build output, and local environments;
- README wording was updated to describe the first public beta, AI assistance, independence, safety boundaries, and licensing.

## Automated validation

The clean public working tree passed:

- 134 unit tests;
- 45 parameterized subtests;
- package-wide Python syntax compilation;
- source-quality validation;
- matching English and Czech locale catalogs;
- validation of 186 themed icons and 6 application-icon files.

The final ZIP archives were also reopened and checked for corruption, generated caches, compiled bytecode, and excluded local-data patterns.

## Physical validation status

Physically confirmed by the maintainer:

- NTAG215 RAW NDEF write and complete readback;
- duplicate URL removal on a physically written tag;
- NTAG215 full known user-area zero and verification;
- read-only NDEF reading and the copyable result popup;
- first write to a fresh CUID with full 1024-byte verification;
- complete current-key read and backup of programmed CUID tags.

Still not physically confirmed:

- destructive NTAG213 and NTAG216 operations;
- replacement of different content on an already-programmed CUID, which remains intentionally blocked;
- a packaged Windows EXE built from this exact public tree;
- every possible Windows DPI, display scaling, Proxmark3 hardware revision, clone vendor, and firmware combination.

## Important limitation

Automated and simulated testing cannot prove that every clone tag or Proxmark3 environment behaves identically. Use disposable or backed-up targets for initial testing, keep the saved operation report, and use the application only with tags and data that you own or are authorized to use.
