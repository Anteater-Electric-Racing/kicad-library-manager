"""Supplier requests use synthetic responses; real manufacturer lookup is checked manually."""

from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.request import Request

from manager import supplier

SAMPLE_URL = "https://www.digikey.com/en/products/detail/yageo/RC0805FR-07243KL/727764"
SPEC_TEXT = """RC0805FR-07243KL
Aliases (RC0805FR07243KL)
YAGEO, RC, Thick Film, SMD Chip, 243 kOhms, 1%, 0805 / 2012
General Information
Supplier                    YAGEO
Case Code  (EIA / mm)        0805 / 2012
Specifications
L        2mm +/-0.1mm        Resistance              243 kOhms
W        1.25mm +/-0.1mm     Resistance Tolerance    1%
T        0.5mm +/-0.1mm      Power                   0.125 W (70C)
                            Voltage DC              150 V (Max Continuous Voltage
                            Temp. Coefficient       -/+100 ppm/C
                            Temperature Range       -55/+155°C
"""


class SupplierTests(unittest.TestCase):
    def test_url_identity_and_host_validation(self):
        self.assertEqual(
            supplier.url_identity(SAMPLE_URL),
            {"MPN": "RC0805FR-07243KL", "Manufacturer": "YAGEO"},
        )
        self.assertEqual(
            supplier.url_identity("www.mouser.com/ProductDetail/KEMET/C0805C?qs=abc")[
                "MPN"
            ],
            "C0805C",
        )
        for url in (
            "https://digikey.com.evil.example/en/products/detail/yageo/part/1",
            "https://www.digikey.com@evil.example/en/products/detail/yageo/part/1",
            "http://www.digikey.com/en/products/detail/yageo/part/1",
        ):
            with self.assertRaises(ValueError):
                supplier.read_product(url)

    def test_structured_data_uses_requested_product(self):
        state = {
            "recommendations": [
                {"@type": "Product", "mpn": "OTHER-PART", "description": "Wrong part"}
            ],
            "product": {
                "ManufacturerProductNumber": "RC0805FR-07243KL",
                "Manufacturer": {"Name": "YAGEO"},
                "Description": {"DetailedDescription": "243 kOhms chip resistor"},
                "DatasheetUrl": "https://example.test/synthetic.pdf",
                "Parameters": [
                    {"ParameterText": "Resistance", "ValueText": "243 kOhms"},
                    {"ParameterText": "Tolerance", "ValueText": "±1%"},
                    {
                        "ParameterText": "Package / Case",
                        "ValueText": "0805 (2012 Metric)",
                    },
                    {"ParameterText": "Power (Watts)", "ValueText": "0.125W, 1/8W"},
                ],
            },
        }
        result = supplier.read_product(
            SAMPLE_URL,
            '<script type="application/json">' + json.dumps(state) + "</script>",
        )
        self.assertEqual(result["part"]["MPN"], "RC0805FR-07243KL")
        self.assertEqual(result["part"]["Value"], "243 kOhms")
        self.assertEqual(result["part"]["Package"], "0805")
        self.assertEqual(result["part"]["Power_W"], "0.125W")
        self.assertEqual(result["provenance"]["method"], "pasted-details")

    @patch(
        "manager.supplier.fetch",
        side_effect=supplier.PageReadError(
            "DigiKey blocked automatic reading (HTTP 403)"
        ),
    )
    @patch("manager.supplier._manufacturer_document", return_value=b"%PDF-fixture")
    @patch("manager.supplier._specsheet_text", return_value=SPEC_TEXT)
    def test_blocked_sample_uses_exact_manufacturer_document(
        self, text, document, fetch
    ):
        result = supplier.read_product(SAMPLE_URL)
        part = result["part"]
        for field, value in {
            "MPN": "RC0805FR-07243KL",
            "Manufacturer": "YAGEO",
            "Value": "243 kOhms",
            "Type": "resistor",
            "Package": "0805",
            "Tolerance": "1%",
            "Power_W": "0.125W",
            "Voltage_VDC": "150V",
        }.items():
            self.assertEqual(part[field], value, field)
        self.assertFalse(part.get("UnitPrice"))
        self.assertFalse(part.get("DistributorStock"))
        self.assertEqual(result["provenance"]["method"], "manufacturer-specsheet")
        self.assertIn(
            "supplier price and stock were not imported", result["warnings"][0]
        )
        document.assert_called_once_with(
            "https://www.yageogroup.com/component-documentation/download/specsheet/RC0805FR-07243KL"
        )

    @patch("manager.supplier.fetch", side_effect=supplier.PageReadError("Blocked"))
    @patch("manager.supplier._manufacturer_document", return_value=b"%PDF-fixture")
    @patch(
        "manager.supplier._specsheet_text",
        return_value=SPEC_TEXT.replace("RC0805FR-07243KL", "WRONG-PART"),
    )
    def test_wrong_manufacturer_part_does_not_supply_ratings(self, *mocks):
        result = supplier.read_product(SAMPLE_URL)
        self.assertEqual(result["provenance"]["method"], "url-identity")
        self.assertNotIn("Value", result["part"])
        self.assertTrue(any("does not identify" in item for item in result["warnings"]))

    @patch("manager.supplier.fetch", side_effect=supplier.PageReadError("Blocked"))
    @patch("manager.supplier._yageo_specsheet")
    def test_unknown_manufacturer_is_identity_only(self, manufacturer, fetch):
        url = "https://www.digikey.com/en/products/detail/example-maker/PART-123/42"
        result = supplier.read_product(content=url)
        self.assertEqual(result["part"]["MPN"], "PART-123")
        self.assertEqual(result["provenance"]["method"], "url-identity")
        self.assertNotIn("Power_W", result["part"])
        manufacturer.assert_not_called()

    def test_supplier_response_and_clipboard_identity_conflict(self):
        content = "Manufacturer: Example\nMPN: DIFFERENT\nDescription: Test chip"
        result = supplier.read_product(SAMPLE_URL, content)
        self.assertEqual(result["part"]["MPN"], "DIFFERENT")
        self.assertTrue(
            any("different part number" in item for item in result["warnings"])
        )

    @patch("manager.supplier._manufacturer_document", return_value=b"%PDF-fixture")
    @patch(
        "manager.supplier._specsheet_text",
        return_value="""SYNTHETIC-CAP
Ceramic capacitor fixture
Chip Size                  0805
Capacitance                0.1 uF
Tolerance                  10%
Voltage DC                 50 VDC
Temp. Coefficient          X7R
""",
    )
    def test_capacitor_specsheet_uses_documented_values(self, *mocks):
        part, _ = supplier._yageo_specsheet(
            {"MPN": "SYNTHETIC-CAP", "Manufacturer": "KEMET"}
        )
        supplier._normalize_product(part)
        self.assertEqual(part["Type"], "capacitor")
        self.assertEqual(part["Value"], "0.1 uF")
        self.assertEqual(part["Voltage_VDC"], "50V")
        self.assertEqual(part["Dielectric"], "X7R")
        self.assertFalse(part.get("Power_W"))

    def test_manufacturer_redirects_stay_on_official_host(self):
        handler = supplier.ManufacturerRedirect()
        for url in (
            "http://www.yageogroup.com/",
            "https://127.0.0.1/",
            "https://www.yageogroup.com.evil.test/",
        ):
            with self.assertRaises(ValueError):
                handler.redirect_request(
                    Request("https://www.yageogroup.com/"), None, 302, "", {}, url
                )

    def test_bundled_pdf_reader_extracts_synthetic_document(self):
        from manager import _vendor  # noqa: F401
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

        writer = PdfWriter()
        page = writer.add_blank_page(612, 792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 50 740 Td (SYNTHETIC-PART) Tj 0 -20 Td (Resistance 243 kOhms) Tj ET"
        )
        page[NameObject("/Contents")] = stream
        buffer = BytesIO()
        writer.write(buffer)
        text = supplier._specsheet_text(buffer.getvalue())
        self.assertIn("SYNTHETIC-PART", text)
        self.assertIn("243 kOhms", text)


if __name__ == "__main__":
    unittest.main()
