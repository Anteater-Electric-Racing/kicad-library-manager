from pathlib import Path
import tempfile
import unittest

from manager import cad, kicad, standard_packages
from manager.importer import ImportSession
from manager.storage import create_library, digest
from manager.sexpr import children, parse


class StandardPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lib = create_library(Path(self.temp.name) / "Library", install_runtime=False)
        self.session = ImportSession()
        self.addCleanup(self.session.close)

    def draft(self, package, pins=3):
        selected = standard_packages.select(self.session, package)
        self.session.upload("symbol.kicad_sym", cad.symbol_library(cad.connector_symbol(pins), "Fixture").encode())
        symbol = next(a["id"] for a in self.session.inventory()["assets"] if a["type"] == ".kicad_sym")
        return dict(mode="bespoke", part=dict(Type="IC", MPN="Fixture", Manufacturer="Test", Package=package),
                    symbolAsset=symbol, symbolName="Fixture", footprintAsset=selected["footprintAsset"],
                    modelAsset=selected["modelAsset"], modelAction="replace", category="components/ICs")

    def test_selection_is_scratch_only_and_rejects_unknown_packages(self):
        before = {p.relative_to(self.lib.root): p.read_bytes() for p in self.lib.root.rglob("*") if p.is_file()}
        for package in standard_packages.inventory():
            result = standard_packages.select(self.session, package["id"])
            self.assertIn(result["footprintAsset"], self.session.assets)
            self.assertIn(result["modelAsset"], self.session.assets)
            for key in ("footprint", "model"):
                self.assertEqual(digest((standard_packages.ROOT / package[key]).read_bytes()), package[key + "SHA256"])
        with self.assertRaisesRegex(ValueError, "bundled standard package"):
            standard_packages.select(self.session, "../../missing")
        self.assertEqual(before, {p.relative_to(self.lib.root): p.read_bytes() for p in self.lib.root.rglob("*") if p.is_file()})
        self.assertEqual(self.lib.rows(), [])

    def test_both_requested_packages_save_with_original_pads_transforms_and_local_models(self):
        for package in ("SOT-23", "TO-220-3_Horizontal_TabDown"):
            with self.subTest(package=package):
                session = ImportSession()
                self.addCleanup(session.close)
                self.session = session
                draft = self.draft(package)
                draft["part"]["MPN"] = package
                proposal = session.prepare(self.lib, draft)
                row = session.commit(self.lib, proposal["token"])
                saved = (self.lib.root / row["FootprintFile"]).read_text()
                source = session.asset(draft["footprintAsset"], [".kicad_mod"])["path"].read_text()
                self.assertEqual(children(parse(source), "pad"), children(parse(saved), "pad"))
                original_model = cad.footprint_data(source)["models"][0]
                actual_model = cad.footprint_data(saved)["models"][0]
                for key in ("offset", "rotate", "scale"):
                    self.assertEqual(original_model[key], actual_model[key])
                model_path = self.lib.root / actual_model["path"].removeprefix("${MYCO_PARTS_DIR}/../")
                self.assertEqual(model_path.read_bytes(), session.asset(draft["modelAsset"], [".step"])["path"].read_bytes())
                self.assertEqual({p["number"] for p in cad.symbol_pins(cad.flatten_symbol((self.lib.root / row["SymbolFile"]).read_text(), row["Symbol"].split(":")[1]))}, {"1", "2", "3"})
                if kicad.cli_path():
                    self.assertTrue(kicad.render("fp", (self.lib.root / row["FootprintFile"]).parent))

    def test_wrong_pin_count_and_missing_symbol_are_rejected(self):
        draft = self.draft("SOT-23-5")
        with self.assertRaisesRegex(ValueError, "pin numbers differ"):
            self.session.prepare(self.lib, draft)
        draft["symbolAsset"] = ""
        with self.assertRaisesRegex(ValueError, "original symbol"):
            self.session.prepare(self.lib, draft)
        self.assertEqual(self.lib.rows(), [])

    def test_existing_library_gets_templates_only_on_successful_save(self):
        import shutil
        templates = self.lib.root / "components/generic_models/standard_packages"
        shutil.rmtree(templates)  # Synthetic library made by a previous app version.
        draft = self.draft("SOT-23")
        proposal = self.session.prepare(self.lib, draft)
        self.assertFalse(templates.exists())
        self.session.commit(self.lib, proposal["token"])
        self.assertTrue((templates / "StandardPackages.pretty/SOT-23.kicad_mod").is_file())
        self.assertTrue((templates / "LICENSE-KICAD.md").is_file())

    def test_changed_existing_template_is_not_overwritten(self):
        draft = self.draft("SOT-23")
        template = self.lib.root / "components/generic_models/standard_packages/StandardPackages.pretty/SOT-23.kicad_mod"
        template.write_text("custom template")
        with self.assertRaisesRegex(ValueError, "different content"):
            self.session.prepare(self.lib, draft)
        self.assertEqual(template.read_text(), "custom template")
