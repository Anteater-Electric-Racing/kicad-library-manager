"""Regressions for the direct-drop editor and component-owned accessories."""

import copy
import json
import subprocess
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from manager import bom, cad, kicad
from manager.importer import ImportSession
from manager.storage import create_library, category_path
from manager.sexpr import children, parse, dump, Quoted as Q
from test_core import FOOTPRINT, SYMBOL


# Synthetic equivalent of the supplier layout: pins and graphics at symbol level.
node = cad.flatten_symbol(SYMBOL, "Header")
for unit in list(children(node, "symbol")):
    node.extend(unit[2:])
    node.remove(unit)
DIRECT_SYMBOL = cad.symbol_library(
    node,
    "SupplierPart",
    {"Manufacturer_Name": "Fixture Corp", "Manufacturer_Part_Number": "PIN-3"},
)


class ImportEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.lib = create_library(self.base / "Library", install_runtime=False)
        self.session = ImportSession()
        self.addCleanup(self.session.close)
        self.session.upload("root/deep/symbol.kicad_sym", DIRECT_SYMBOL.encode())
        self.session.upload("root/deep/footprint.kicad_mod", FOOTPRINT.encode())
        assets = self.session.inventory()["assets"]
        self.draft = dict(
            mode="bespoke",
            part=dict(MPN="PIN-3", Manufacturer="Fixture Corp", Type="connector"),
            category="connectors",
            symbolName="SupplierPart",
            symbolAsset=next(a["id"] for a in assets if a["type"] == ".kicad_sym"),
            footprintAsset=next(a["id"] for a in assets if a["type"] == ".kicad_mod"),
        )

    def save(self, draft=None):
        return self.session.commit(
            self.lib, self.session.prepare(self.lib, draft or self.draft)["token"]
        )

    def test_supplier_direct_pins_match_and_save_without_renumbering(self):
        before = cad.symbol_pins(cad.flatten_symbol(DIRECT_SYMBOL, "SupplierPart"))
        self.assertEqual([p["number"] for p in before], ["1", "2", "3"])
        info, _ = self.session.inspect(self.draft)
        self.assertTrue(info["inference"]["eligible"])
        saved = self.save()
        after = cad.symbol_pins(
            cad.flatten_symbol(
                (self.lib.root / saved["SymbolFile"]).read_text(), "PIN-3"
            )
        )
        self.assertEqual(
            [{k: v for k, v in p.items() if k != "unit"} for p in before],
            [{k: v for k, v in p.items() if k != "unit"} for p in after],
        )
        self.assertEqual(saved["Category"], "components/connectors")
        with zipfile.ZipFile(
            next((self.lib.appdata / "original-downloads").glob("*.zip"))
        ) as archive:
            self.assertEqual(
                archive.read("originals/root/deep/symbol.kicad_sym"),
                DIRECT_SYMBOL.encode(),
            )

    def test_unique_leaf_inheritance_infers_identity_and_inherits_direct_pins(self):
        tree = parse(DIRECT_SYMBOL)
        tree += [
            [
                "symbol",
                Q("Child"),
                ["extends", Q("SupplierPart")],
                ["property", Q("Manufacturer_Part_Number"), Q("CHILD-3")],
            ]
        ]
        text = dump(tree)
        self.assertEqual(cad.symbol_choices(text), ["Child"])
        self.session.upload("inherited.kicad_sym", text.encode())
        asset = next(
            a
            for a in self.session.inventory()["assets"]
            if a["label"] == "inherited.kicad_sym"
        )
        self.assertEqual(asset["suggestedSymbol"], "Child")
        self.assertEqual(asset["metadata"]["Child"]["MPN"], "CHILD-3")
        self.assertEqual(len(cad.symbol_pins(cad.flatten_symbol(text, "Child"))), 3)
        tree += [["symbol", Q("Sibling"), ["extends", Q("SupplierPart")]]]
        self.assertEqual(
            cad.symbol_metadata(cad.flatten_symbol(dump(tree), "Sibling"), tree[-1])[
                "MPN"
            ],
            "Sibling",
        )
        self.assertEqual(cad.symbol_choices(dump(tree)), ["Child", "Sibling"])

    def test_category_shorthand_and_reserved_paths(self):
        for text, expected in [
            ("connectors", "components/connectors"),
            (" components/connectors ", "components/connectors"),
            ("Components/board headers", "components/board headers"),
            ("components", "components"),
            ("generic_models_backup", "components/generic_models_backup"),
        ]:
            self.assertEqual(category_path(text), expected)
        for path in [
            "../outside",
            "/components/connectors",
            "generic_models",
            "components/generic_models/x",
            "components/Generic_Models/x",
            "logos",
            "C:\\library",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                category_path(path)

    def test_both_body_styles_preserve_pin_identities_and_native_render(self):
        self.draft.update(alternative=True, layout="split", pinsConfirmed=True)
        saved = self.save()
        node = cad.flatten_symbol(
            (self.lib.root / saved["SymbolFile"]).read_text(), "PIN-3"
        )
        pins = cad.symbol_pins(node)
        for style in ["1", "2"]:
            selected = [p for p in pins if p["unit"].endswith("_" + style)]
            self.assertEqual({p["number"] for p in selected}, {"1", "2", "3"})
            self.assertEqual({p["type"] for p in selected}, {"passive"})
        self.assertNotEqual([p["x"] for p in pins[:3]], [p["x"] for p in pins[3:]])
        if kicad.cli_path():
            self.assertTrue(
                kicad.render("sym", self.lib.root / saved["SymbolFile"], "PIN-3")
            )
            output = self.base / "native-roundtrip.kicad_sym"
            subprocess.run(
                [
                    kicad.cli_path(),
                    "sym",
                    "upgrade",
                    "--force",
                    "--output",
                    str(output),
                    str(self.lib.root / saved["SymbolFile"]),
                ],
                capture_output=True,
                check=True,
            )
            roundtrip = cad.symbol_pins(cad.flatten_symbol(output.read_text(), "PIN-3"))
            self.assertEqual(
                {p["unit"].rsplit("_", 1)[1] for p in roundtrip}, {"1", "2"}
            )
            self.assertEqual(len(roundtrip), 6)
        edit = ImportSession()
        self.addCleanup(edit.close)
        draft = edit.load_existing(self.lib, saved["ID"])["draft"]
        draft["part"]["Notes"] = "Keep both styles"
        result = edit.commit(self.lib, edit.prepare(self.lib, draft)["token"], True)
        self.assertEqual(
            len(
                cad.symbol_pins(
                    cad.flatten_symbol(
                        (self.lib.root / result["SymbolFile"]).read_text(), "PIN-3"
                    )
                )
            ),
            6,
        )

    def test_live_preview_does_not_require_metadata_or_pin_confirmation_or_write_library(
        self,
    ):
        before = {
            p.relative_to(self.lib.root): p.read_bytes()
            for p in self.lib.root.rglob("*")
            if p.is_file()
        }
        draft = copy.deepcopy(self.draft)
        draft.update(part={}, alternative=True, layout="split", pinsConfirmed=False)
        if kicad.cli_path():
            preview = self.session.preview(draft)
            self.assertEqual(len(preview["svgs"]), 2)
            self.assertEqual(len(preview["originals"]), 1)
            self.assertTrue(
                all("<svg" in s for s in preview["svgs"] + preview["originals"])
            )
        self.assertIsNone(self.session.prepared)
        self.assertEqual(
            before,
            {
                p.relative_to(self.lib.root): p.read_bytes()
                for p in self.lib.root.rglob("*")
                if p.is_file()
            },
        )
        with self.assertRaisesRegex(ValueError, "Check the inferred pin list"):
            self.session.prepare(
                self.lib, dict(self.draft, alternative=True, pinsConfirmed=False)
            )

    def test_connector_ratings_persist_in_catalog_database_and_kicad_fields(self):
        self.draft["part"].update(Current_A="5 A", Voltage_V="250 V")
        row = self.save()
        self.assertEqual((row["Current_A"], row["Voltage_V"]), ("5", "250"))
        with sqlite3.connect(self.lib.appdata / "parts.sqlite") as conn:
            self.assertEqual(
                conn.execute("SELECT Current_A, Voltage_V FROM components").fetchone(),
                ("5", "250"),
            )
        conn.close()
        fields = json.loads((self.lib.appdata / "parts.kicad_dbl").read_text())[
            "libraries"
        ][0]["fields"]
        self.assertTrue({"Current_A", "Voltage_V"} <= {f["column"] for f in fields})

    def test_invalid_ratings_do_not_save(self):
        for bad in ["-1", "0", "NaN", "wrong"]:
            self.draft["part"]["Current_A"] = bad
            with self.assertRaisesRegex(ValueError, "positive rating"):
                self.session.prepare(self.lib, self.draft)
        self.assertEqual(self.lib.rows(), [])

    def test_accessories_only_created_with_parent_and_bom_survives_edit(self):
        with self.assertRaisesRegex(ValueError, "owning component"):
            self.session.prepare(
                self.lib,
                dict(
                    mode="accessory",
                    part=dict(MPN="CRIMP", Manufacturer="Fixture", Type="accessory"),
                ),
            )
        self.draft["recipe"] = {
            "items": [
                dict(manufacturer="Fixture", mpn="CRIMP", quantity=3, role="crimp")
            ]
        }
        proposal = self.session.prepare(self.lib, self.draft)
        self.assertEqual(
            self.lib.rows(), []
        )  # cancellation has no staged catalog side effects
        parent = self.session.commit(self.lib, proposal["token"])
        crimp = next(r for r in self.lib.rows() if r["Type"] == "accessory")
        instances = [
            dict(ref="J1", partID=parent["ID"], libraryID=self.lib.id),
            dict(ref="J2", partID=parent["ID"], libraryID=self.lib.id),
        ]
        expanded = bom.expand(self.lib, instances)
        self.assertEqual(
            next(r for r in expanded["purchasing"] if r["PartID"] == crimp["ID"])[
                "Quantity"
            ],
            6,
        )
        edit = ImportSession()
        self.addCleanup(edit.close)
        draft = edit.load_existing(self.lib, parent["ID"])["draft"]
        draft["recipe"]["items"][0]["quantity"] = 2
        edit.commit(self.lib, edit.prepare(self.lib, draft)["token"], True)
        self.assertEqual(
            next(
                r
                for r in bom.expand(self.lib, instances)["purchasing"]
                if r["PartID"] == crimp["ID"]
            )["Quantity"],
            4,
        )
        self.assertEqual(
            len([r for r in self.lib.rows() if r["Type"] == "accessory"]), 1
        )

    def test_accessory_and_parent_rollback_together_on_failure(self):
        self.draft["recipe"] = {
            "items": [dict(manufacturer="Fixture", mpn="CRIMP", quantity=3)]
        }
        proposal = self.session.prepare(self.lib, self.draft)
        original = self.lib._replace

        def fail_database(path, data):
            if path.name == "parts.sqlite":
                raise OSError("simulated save failure")
            return original(path, data)

        with patch.object(self.lib, "_replace", side_effect=fail_database):
            with self.assertRaises(OSError):
                self.session.commit(self.lib, proposal["token"])
        # Recovery may be needed when an injected persistent failure also blocks rollback.
        if (self.lib.appdata / "pending-transaction.json").exists():
            self.lib.recover(writer_stopped=True)
        self.assertEqual(self.lib.rows(), [])

    def test_drill_slot_and_offset_are_retained(self):
        text = FOOTPRINT.replace("(drill 1)", "(drill oval 1 2 (offset 0.25 -0.3))", 1)
        pad = cad.footprint_data(text)["pads"][0]
        self.assertEqual(
            (pad["drillWidth"], pad["drillHeight"], pad["drillOffset"]),
            (1, 2, [0.25, -0.3]),
        )


if __name__ == "__main__":
    unittest.main()
