"""Copy-only legacy migration checks, always using synthetic source libraries."""

import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from manager import cad
from manager.migration import audit_legacy, inventory, migrate_legacy
from manager.sexpr import children, parse
from manager.storage import Library


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Old library"
        self.destination = self.root / "New library"
        (self.source / "parts-library-appdata").mkdir(parents=True)
        (self.source / "symbol").mkdir()
        (self.source / "footprints/Headers.pretty").mkdir(parents=True)
        (self.source / "STEP").mkdir()
        (self.source / "Component downloads/Passives").mkdir(parents=True)
        (self.source / "Component downloads/Passives/source-only.pdf").write_bytes(
            b"original passive PDF"
        )
        (self.source / "Component downloads/original.zip").write_bytes(
            b"original unmodified archive"
        )
        (self.source / "STEP/header.step").write_bytes(b"synthetic model fixture")
        self.symbol = cad.symbol_library(
            cad.connector_symbol(2, "single", name="Header"), "Header"
        )
        (self.source / "symbol/Headers.kicad_sym").write_text(self.symbol)
        self.footprint = """(footprint "Header" (version 20241229) (generator pcbnew) (layer "F.Cu")
            (pad "1" thru_hole rect (at 0 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask"))
            (pad "2" thru_hole circle (at 2.54 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask"))
            (model "${MYCO_PARTS_DIR}/STEP/header.step" (at (xyz 0.2 -0.1 0.03)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 90))))"""
        (self.source / "footprints/Headers.pretty/Header.kicad_mod").write_text(
            self.footprint
        )
        (self.source / "Virtus Logo.kicad_mod").write_text(
            '(footprint "Virtus Logo" (layer "F.Cu"))'
        )
        (self.source / "parts-library-appdata/LICENSE.md").write_text(
            "Synthetic fixture license"
        )
        self.rows = [
            {
                "ID": "001-HEADER",
                "MPN": "001-HEADER",
                "Manufacturer": "FixtureCo",
                "Value": "Header",
                "Symbol": "Headers:Header",
                "Footprint": "Headers:Header",
                "Reference": "J",
                "Category": "connector",
                "Folder": "symbol/connector/fixture-family",
                "Status": "needs_review",
                "Datasheet": "https://example.invalid/data.pdf",
                "TemperatureCoefficient": "25ppm/°C",
                "DistributorStock": "100",
                "Notes": "Keep this note",
            }
        ]
        self.write_catalog()

    def write_catalog(self):
        fields = list(dict.fromkeys(key for row in self.rows for key in row))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(self.rows)
        (self.source / "parts-library-appdata/components.csv").write_text(
            stream.getvalue(), newline=""
        )

    def test_preserves_ids_originals_geometry_transforms_and_source(self):
        before = inventory(self.source)
        report = migrate_legacy(self.source, self.destination, install_runtime=False)
        lib = Library(self.destination)
        row = lib.rows()[0]
        self.assertEqual(row["ID"], "001-HEADER")
        self.assertEqual(row["Status"], "")
        self.assertEqual(row["Category"], "components/connectors/fixture-family")
        self.assertIn("TemperatureCoefficient: 25ppm/°C", row["Notes"])
        self.assertEqual(row["Datasheet"], self.rows[0]["Datasheet"])
        self.assertEqual(inventory(self.source), before)
        copied = parse((lib.root / row["FootprintFile"]).read_text())
        original = parse(self.footprint)
        self.assertEqual(children(copied, "pad"), children(original, "pad"))
        self.assertEqual(
            children(copied, "model")[0][2:], children(original, "model")[0][2:]
        )
        self.assertIn(
            "components/connectors/fixture-family", children(copied, "model")[0][1]
        )
        pins = cad.symbol_pins(
            cad.flatten_symbol((lib.root / row["SymbolFile"]).read_text(), "Header")
        )
        self.assertEqual(
            pins, cad.symbol_pins(cad.flatten_symbol(self.symbol, "Header"))
        )
        self.assertEqual(lib.recipe(row), {"version": 1, "items": []})
        self.assertTrue(report["sourceUnchanged"])
        self.assertFalse(report["registrationsChanged"])
        self.assertEqual(report["rows"][0]["sourceRow"], self.rows[0])
        self.assertEqual(
            (lib.appdata / "original-downloads/legacy/original.zip").read_bytes(),
            b"original unmodified archive",
        )
        self.assertEqual(
            (
                lib.appdata / "original-downloads/legacy/Passives/source-only.pdf"
            ).read_bytes(),
            b"original passive PDF",
        )
        self.assertFalse(list((lib.root / "components").rglob("*.pdf")))
        with zipfile.ZipFile(
            lib.appdata / "migration/legacy-source-snapshot.zip"
        ) as archive:
            self.assertEqual(set(archive.namelist()), set(before))
            self.assertEqual(
                archive.read("parts-library-appdata/components.csv"),
                (self.source / "parts-library-appdata/components.csv").read_bytes(),
            )
        self.assertEqual(
            set(p.name for p in lib.root.iterdir()), {"components", "appdata"}
        )
        self.assertTrue(list((lib.root / "components/logos").rglob("*.kicad_mod")))

    def test_passives_share_files_without_component_folders(self):
        self.rows = [
            {
                **self.rows[0],
                "ID": ident,
                "MPN": ident,
                "Category": "resistor",
                "Type": "R",
                "Reference": "R",
                "Folder": "",
                "Package": "0805",
            }
            for ident in ["R-FIRST", "R-SECOND"]
        ]
        self.write_catalog()
        migrate_legacy(self.source, self.destination, install_runtime=False)
        lib = Library(self.destination)
        rows = lib.rows()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not r["AssetFolder"] for r in rows))
        self.assertEqual(rows[0]["SymbolFile"], rows[1]["SymbolFile"])
        self.assertEqual(rows[0]["FootprintFile"], rows[1]["FootprintFile"])
        self.assertFalse(list((lib.root / "components").rglob("component.json")))

    def test_missing_model_is_reported_and_retained(self):
        (self.source / "STEP/header.step").unlink()
        report = migrate_legacy(self.source, self.destination, install_runtime=False)
        self.assertEqual(report["warnings"][0]["kind"], "missing-model")
        row = Library(self.destination).rows()[0]
        model = children(
            parse((self.destination / row["FootprintFile"]).read_text()), "model"
        )[0]
        self.assertEqual(model[1], "${MYCO_PARTS_DIR}/STEP/header.step")

    def test_errors_never_publish_partial_destination_or_change_source(self):
        (self.source / "symbol/Headers.kicad_sym").unlink()
        before = inventory(self.source)
        self.assertTrue(audit_legacy(self.source)["errors"])
        with self.assertRaisesRegex(ValueError, "locate symbol"):
            migrate_legacy(self.source, self.destination, install_runtime=False)
        self.assertFalse(self.destination.exists())
        self.assertEqual(inventory(self.source), before)
        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, "already exist"):
            migrate_legacy(self.source, self.destination, install_runtime=False)

    def test_source_symlinks_rejected_before_conversion(self):
        outside = self.root / "outside.txt"
        outside.write_text("not library data")
        try:
            (self.source / "shortcut").symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "symlink"):
            migrate_legacy(self.source, self.destination, install_runtime=False)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
