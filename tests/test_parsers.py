from __future__ import annotations

import unittest

from bambu_rfid_diag.models import TagInfo
from bambu_rfid_diag.parsers import (
    enrich_mfu_info,
    enrich_mifare_info,
    parse_default_key_check,
    parse_hardware,
    parse_iso14a,
)


HARDWARE_AND_TAG = """
[+] Using UART port COM8
[+] Communicating with PM3 over USB-CDC

  [ Proxmark3 ]

    MCU....... AT91SAM7S512 Rev B
    Memory.... 512 KB ( 74% used )
    Target.... PM3 GENERIC

    Client.... Iceman/master/v4.21611-604-g53b4e2095 2026-07-29 01:14:01
    Bootrom... Iceman/master/v4.21611-604-g53b4e2095-suspect 2026-07-29 01:12:04 567cf9c5f
    OS........ Iceman/master/v4.21611-604-g53b4e2095-suspect 2026-07-29 01:12:24 567cf9c5f

[+]  UID: DE AD BE EF
[+] ATQA: 00 04
[+]  SAK: 08 [2]
[+] Possible types:
[+]    MIFARE Classic 1K / Classic 1K CL2
"""


RAW_HW_VERSION_20260729 = """
[+] Using UART port COM8
[+] Communicating with PM3 over USB-CDC

 [ Proxmark3 ]

 [ Client ]
  Iceman/master/v4.21611-604-g53b4e2095-suspect 2026-07-29 01:14:01 567cf9c5f
  Compiler.................. MinGW-w64 16.1.0

 [ Model ]
  Firmware.................. PM3 GENERIC

 [ ARM ]
  Bootrom.... Iceman/master/v4.21611-604-g53b4e2095-suspect 2026-07-29 01:12:04 567cf9c5f
  OS......... Iceman/master/v4.21611-604-g53b4e2095-suspect 2026-07-29 01:12:24 567cf9c5f

 [ Hardware ]
  --= uC: AT91SAM7S512 Rev B
  --= Embedded Processor: ARM7TDMI
  --= Internal SRAM size: 64K bytes
  --= Architecture identifier: AT91SAM7Sxx Series
  --= Embedded flash memory 512K bytes ( 74% used )
"""


def key_table(failing_sector: int | None = None) -> str:
    lines = ["[+] | Sec | key A        |res| key B        |res|"]
    for sector in range(16):
        result_b = 0 if sector == failing_sector else 1
        lines.append(
            f"[+] | {sector:03d} | FFFFFFFFFFFF | 1 | FFFFFFFFFFFF | {result_b} |"
        )
    return "\n".join(lines)


REAL_CUID_OUTPUT_20260802 = """
[+]  UID: AA 7C 25 A6   ( ONUID, re-used )
[+] ATQA: 00 04
[+]  SAK: 08 [2]
[+]    MIFARE Classic 1K

[=] --- Fingerprint
[+] Fudan based card

[+] Magic capabilities... Gen 2 / CUID
[+] Prng....... weak

[+] -----+-----+--------------+---+--------------+----
[+]  Sec | Blk | key A        |res| key B        |res
[+] -----+-----+--------------+---+--------------+----
""" + "\n".join(
    f"[+]  {sector:03d} | {sector * 4 + 3:03d} | FFFFFFFFFFFF | 1 | FFFFFFFFFFFF | 1"
    for sector in range(16)
) + """
[+] -----+-----+--------------+---+--------------+----
[+] ( 0:Failed / 1:Success )
"""


class ParserTests(unittest.TestCase):
    def test_hardware_and_versions_from_real_build_shape(self) -> None:
        info = parse_hardware(HARDWARE_AND_TAG)
        self.assertTrue(info.connected)
        self.assertEqual(info.port, "COM8")
        self.assertEqual(info.mcu, "AT91SAM7S512 Rev B")
        self.assertEqual(info.target, "PM3 GENERIC")
        self.assertTrue(info.version_match)

    def test_hardware_and_versions_from_actual_hw_version_output(self) -> None:
        info = parse_hardware(RAW_HW_VERSION_20260729)
        self.assertTrue(info.connected)
        self.assertEqual(info.port, "COM8")
        self.assertEqual(info.communication, "USB-CDC")
        self.assertEqual(info.mcu, "AT91SAM7S512 Rev B")
        self.assertEqual(info.memory, "512K bytes ( 74% used )")
        self.assertEqual(info.target, "PM3 GENERIC")
        self.assertIn("g53b4e2095-suspect", info.client_version or "")
        self.assertTrue(info.version_match)

    def test_classifies_mifare_classic_1k(self) -> None:
        tag = parse_iso14a(HARDWARE_AND_TAG)
        self.assertTrue(tag.present)
        self.assertEqual(tag.uid, "DE AD BE EF")
        self.assertEqual(tag.atqa, "00 04")
        self.assertEqual(tag.sak, "08")
        self.assertEqual(tag.family, "mfc1k")

    def test_magic_detection_and_all_default_keys(self) -> None:
        output = """
        [=] --- Magic Tag Information
        [+] Magic capabilities... Gen 2 / CUID
        [+] Fingerprint........... Fudan based card
        [=] --- PRNG Information
        [+] Prng................. weak
        """ + key_table()
        tag = enrich_mifare_info(parse_iso14a(HARDWARE_AND_TAG), output)
        all_default, sectors = parse_default_key_check(output)
        self.assertEqual(tag.magic_kind, "CUID / Magic Gen2")
        self.assertEqual(tag.prng, "weak")
        self.assertTrue(all_default)
        self.assertEqual(sectors, 16)

    def test_actual_20260802_cuid_output(self) -> None:
        tag = parse_iso14a(REAL_CUID_OUTPUT_20260802)
        enrich_mifare_info(tag, REAL_CUID_OUTPUT_20260802)
        all_default, sectors = parse_default_key_check(REAL_CUID_OUTPUT_20260802)

        self.assertEqual(tag.uid, "AA 7C 25 A6")
        self.assertEqual(tag.family, "mfc1k")
        self.assertEqual(tag.magic_kind, "CUID / Magic Gen2")
        self.assertEqual(tag.fingerprint, "Fudan (identified from client output)")
        self.assertEqual(tag.prng, "weak")
        self.assertTrue(all_default)
        self.assertEqual(sectors, 16)

    def test_one_failed_key_is_not_fresh(self) -> None:
        all_default, sectors = parse_default_key_check(key_table(failing_sector=7))
        self.assertFalse(all_default)
        self.assertEqual(sectors, 16)

    def test_ntag215_configuration_and_lock_pages(self) -> None:
        output = """
        [+] TYPE: NTAG 215 504bytes (NT2H1511G0DUx)
        [+] UID: 04 C1 3A AB 7E 26 81
        [+] Lock: 00 00 - 0000000000000000
        [=] cfg0 [131/0x83]: 04 00 00 FF
        [=] - pages don't need authentication
        [=] Block#. | Data        | Ascii
        [+] 130/0x82 | 00 00 00 BD | ....
        [=] Block#. | Data        | Ascii
        [+] 131/0x83 | 04 00 00 FF | ....
        [=] TAG IC Signature: 00000000000000000000000000000000
        [=]                 : 00000000000000000000000000000000
        [+] Signature verification: failed
        """
        tag = TagInfo(present=True, family="type2")
        enrich_mfu_info(tag, output)
        self.assertEqual(tag.family, "ntag215")
        self.assertEqual(tag.static_lock, "00 00")
        self.assertEqual(tag.dynamic_lock, "00 00 00")
        self.assertEqual(tag.auth0, "FF")
        self.assertEqual(tag.originality_signature, "0" * 64)
        self.assertFalse(tag.originality_verified)
        self.assertTrue(tag.future_write_ready)

    def test_no_tag_is_not_misreported(self) -> None:
        tag = parse_iso14a("[-] No known/supported 13.56 MHz tags found")
        self.assertFalse(tag.present)
        self.assertEqual(tag.family, "unknown")

    def test_firmware_hash_mismatch_is_detected(self) -> None:
        output = HARDWARE_AND_TAG.replace(
            "OS........ Iceman/master/v4.21611-604-g53b4e2095-suspect",
            "OS........ Iceman/master/v4.21611-604-g123456789-suspect",
        )
        self.assertFalse(parse_hardware(output).version_match)

    def test_locked_ntag_is_not_ready(self) -> None:
        output = """
        [+] TYPE: NTAG 215 504bytes
        [+] Lock: 00 00 - 0000000000000000
        [=] cfg0 [131/0x83]: 04 00 00 FF
        [+] 130/0x82 | 04 00 00 BD | ....
        [+] 131/0x83 | 04 00 00 FF | ....
        """
        tag = enrich_mfu_info(TagInfo(present=True, family="type2"), output)
        self.assertFalse(tag.future_write_ready)
        self.assertIn("lock bits", tag.readiness_detail or "")


if __name__ == "__main__":
    unittest.main()
