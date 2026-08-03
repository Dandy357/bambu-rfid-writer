# Tag support and validation status

## Status meanings

- **Physically confirmed:** observed on the user's Proxmark3 and tag.
- **Automated only:** covered by simulated command/output tests, not hardware-confirmed.
- **Read-only:** diagnostics are allowed but destructive operations are intentionally blocked.

## MIFARE Classic / Bambu

| Scenario | Status | Notes |
|---|---|---|
| Fresh CUID/Gen2 first write | Physically confirmed in v0.4.0.2 | Complete 1024-byte verification succeeded. |
| Read and back up known programmed CUID | Physically confirmed | Current UID key file opened all 64 blocks and a 1024-byte backup was persisted. |
| Same-source programmed CUID | Automated no-change path | Exact 1024/1024 match stops without a probe or restore. |
| Different-source programmed CUID | Unsupported | The stable workflow blocks before every destructive command. A chip-specific Magic/backdoor mechanism is not inferred. |
| Restore programmed CUID with `--ka` | Low-level capability only | The stable UI workflow does not use this path for different programmed content. |
| Programmed target absent from library | Blocked | Current sector keys are not known. |
| Duplicate current UID in library | Blocked | Authentication source is ambiguous. |
| Ordinary non-writable MIFARE Classic | Intended to block | Fresh-target Magic/type and key checks must fail closed. |

## NFC Type 2

| Profile | Write/erase implementation | Physical status |
|---|---|---|
| NXP NTAG213 | Known layout | Automated only |
| NXP NTAG215 | Known layout | RAW NDEF write, duplicate-URL fix, and full user-area zero physically confirmed after the refactor |
| NXP NTAG216 | Known layout | Automated only |
| Generic NFC Forum Type 2 | Diagnostics and NDEF reading | Write blocked because CC data alone does not define every protected/reserved region |
| Other-vendor Type 2 | Diagnostics and best-effort NDEF reading unless an explicit write profile is added | No write profile is inferred merely from capacity similarity |

## Read-only protocol actions

- **Check CUID** accepts only a MIFARE Classic 1K target and does not fall through to Type 2 diagnostics.
- **Check NDEF** accepts only an NFC Type 2 target and does not run MIFARE Classic key checks.
- **Read NDEF** creates a temporary MFU dump, decodes supported Text and URI records, displays unsupported records conservatively, and removes the temporary files.
- NDEF reading and the copyable result dialog were physically confirmed by the maintainer in version 0.9.2 and remain included in 0.9.3.

## Originality signatures

Originality and practical NDEF compatibility are separate states. An invalid, zero, unavailable, or unsupported signature is a non-blocking provenance warning. It does not by itself prove that a tag cannot store NDEF.

## Required physical test order

1. NTAG215 write with Recommended profile.
2. NTAG215 safe NDEF clear.
3. NTAG215 full user-area zero.
4. Fresh CUID first-write regression.
5. Known programmed CUID exact-match no-change result.
6. Keep different-source programmed-CUID rewrite disabled for the 1.0 acceptance test.
7. Investigate it only as a separate future feature on disposable tags.
8. NTAG213 write/clear/zero.
9. NTAG216 write/clear/zero.
10. Cancellation during a long real PM3 operation.
