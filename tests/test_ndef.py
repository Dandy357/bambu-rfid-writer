from __future__ import annotations

import unittest
from pathlib import Path

from bambu_rfid_diag.ndef import (
    NtagField,
    build_filament_ndef,
    build_ntag_ndef,
    parse_mfu_dump,
    parse_ndef_message,
)


URL = "https://example.com/filament/sample?id=12345"
TEXT = "Example Filaments\nPETG Blue\nPurchased 07. 2026"

# This synthetic TLV fixture contains no real tag UID, product identifier, or purchase data.
EXPECTED_TLV_HEX = (
    "035e91012555046578616d706c652e636f6d2f66696c616d656e742f73616d706c653f"
    "69643d31323334355101315402656e4578616d706c652046696c616d656e74730a504554"
    "4720426c75650a5075726368617365642030372e2032303236fe"
)


class NdefTests(unittest.TestCase):
    def test_builder_reproduces_synthetic_sample_byte_for_byte(self) -> None:
        generated = build_filament_ndef(
            brand="Example Filaments",
            filament_type="PETG Blue",
            purchase_date="07. 2026",
            url=URL,
            locale="en",
        )
        expected = bytes.fromhex(EXPECTED_TLV_HEX)
        sample_path = Path(__file__).parent / "fixtures" / "hf-mfu-sample.bin"
        sample = parse_mfu_dump(sample_path.read_bytes(), locale="en")
        actual_tlv = sample.pages[4 * 4 : 4 * 4 + len(expected)]
        self.assertEqual(actual_tlv, expected)
        self.assertEqual(generated, actual_tlv)

    def test_uri_and_text_decode(self) -> None:
        tlv = bytes.fromhex(EXPECTED_TLV_HEX)
        self.assertEqual(tlv[0], 0x03)
        message_length = tlv[1]
        records = parse_ndef_message(tlv[2 : 2 + message_length], locale="en")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].decoded_value(), URL)
        self.assertEqual(records[1].decoded_value(), TEXT)

    def test_rejects_non_web_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "must begin with https:// or http://"):
            build_filament_ndef("SUNLU", "PETG Grey", "07. 2026", "example.com")

    def test_incomplete_web_url_has_a_specific_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "Enter a complete web address"):
            build_filament_ndef("SUNLU", "PETG Grey", "07. 2026", "https://")

    def test_rejects_control_characters_in_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "control characters"):
            build_filament_ndef(
                "SUNLU\nInjected",
                "PETG Grey",
                "07. 2026",
                "https://example.com",
            )

    def test_utf8_text_is_preserved(self) -> None:
        tlv = build_filament_ndef(
            "Café Filaments",
            "PETG Blue – Premium",
            "07. 2026",
            "https://example.com/filament",
        )
        length_offset = 2 if tlv[1] != 0xFF else 4
        length = tlv[1] if tlv[1] != 0xFF else int.from_bytes(tlv[2:4], "big")
        records = parse_ndef_message(
            tlv[length_offset : length_offset + length], locale="en"
        )
        self.assertEqual(
            records[1].decoded_value(),
            "Café Filaments\nPETG Blue – Premium\nPurchased 07. 2026",
        )

    def test_ordered_fields_and_write_name_flags(self) -> None:
        tlv = build_ntag_ndef(
            [
                NtagField("Brand", "SUNLU", True),
                NtagField("Filament / colour", "PETG Grey", False),
                NtagField("Diameter", "1.75 mm", True),
                NtagField("Link", "https://example.com/petg", False, kind="uri"),
            ],
            language="en",
            locale="en",
        )
        offset = 2 if tlv[1] != 0xFF else 4
        length = tlv[1] if tlv[1] != 0xFF else int.from_bytes(tlv[2:4], "big")
        records = parse_ndef_message(tlv[offset : offset + length], locale="en")
        self.assertEqual(records[0].type, b"T")
        self.assertEqual(
            records[0].decoded_value(),
            "Brand SUNLU\nPETG Grey\nDiameter 1.75 mm",
        )
        self.assertEqual(records[1].type, b"U")
        self.assertEqual(records[1].decoded_value(), "https://example.com/petg")

    def test_uri_position_splits_text_groups_and_preserves_exact_order(self) -> None:
        tlv = build_ntag_ndef(
            [
                NtagField("Brand", "SUNLU", False),
                NtagField("Link", "https://example.com", kind="uri"),
                NtagField("Material", "PLA", False),
            ],
            locale="en",
        )
        offset = 2 if tlv[1] != 0xFF else 4
        length = tlv[1] if tlv[1] != 0xFF else int.from_bytes(tlv[2:4], "big")
        records = parse_ndef_message(tlv[offset : offset + length], locale="en")
        self.assertEqual([record.type for record in records], [b"T", b"U", b"T"])
        self.assertEqual(records[0].decoded_value(), "SUNLU")
        self.assertEqual(records[1].decoded_value(), "https://example.com")
        self.assertEqual(records[2].decoded_value(), "PLA")

    def test_text_only_message_is_supported(self) -> None:
        tlv = build_ntag_ndef([NtagField("Material", "PLA")], locale="en")
        offset = 2 if tlv[1] != 0xFF else 4
        length = tlv[1] if tlv[1] != 0xFF else int.from_bytes(tlv[2:4], "big")
        records = parse_ndef_message(tlv[offset : offset + length], locale="en")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].type, b"T")
        self.assertEqual(records[0].decoded_value(), "PLA")

    def test_uri_only_message_is_supported(self) -> None:
        tlv = build_ntag_ndef(
            [NtagField("Link", "https://example.com", kind="uri")], locale="en"
        )
        offset = 2 if tlv[1] != 0xFF else 4
        length = tlv[1] if tlv[1] != 0xFF else int.from_bytes(tlv[2:4], "big")
        records = parse_ndef_message(tlv[offset : offset + length], locale="en")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].type, b"U")

    def test_more_than_one_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only one URL field"):
            build_ntag_ndef(
                [
                    NtagField("Link 1", "https://example.com/1", kind="uri"),
                    NtagField("Link 2", "https://example.com/2", kind="uri"),
                ],
                locale="en",
            )

    def test_empty_field_list_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one field"):
            build_ntag_ndef([], locale="en")

    def test_content_over_ntag215_capacity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds the available NDEF capacity"):
            build_filament_ndef(
                "SUNLU", "X" * 480, "07. 2026", "https://example.com"
            )


if __name__ == "__main__":
    unittest.main()
