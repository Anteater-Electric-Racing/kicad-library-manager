"""Metadata edits keep migrated CAD and model assemblies intact."""

from pathlib import Path
import tempfile
import unittest

from manager import cad
from manager.importer import ImportSession
from manager.sexpr import children, parse, dump, Quoted as Q
from manager.storage import COLUMNS, create_library, csv_bytes, json_bytes


class EditPreservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.lib = create_library(
            Path(temporary.name) / "Library", install_runtime=False
        )

    def write(self, name, content):
        path = self.lib.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def component(self, *, shared=False, symbol=True, footprint=True, models=None):
        folder = (
            "components/generic_models/legacy/resistors"
            if shared
            else "components/connectors/header"
        )
        row = {key: "" for key in COLUMNS}
        row.update(
            ID="PART",
            MPN="PART",
            Manufacturer="Fixture",
            Value="10k" if shared else "Header",
            Type="resistor" if shared else "connector",
            Package="0805" if shared else "",
            Tolerance="1%",
            Power_W="0.125",
            Category="components/resistors" if shared else "components/connectors",
            AssetFolder="" if shared else folder,
        )
        if symbol:
            row.update(
                Symbol="fixture:Original", SymbolFile=folder + "/symbol.kicad_sym"
            )
            self.write(
                row["SymbolFile"],
                cad.symbol_library(cad.connector_symbol(2), "Original"),
            )
        if footprint:
            row.update(
                Footprint="fixture:Original",
                FootprintFile=folder + "/footprint.pretty/Original.kicad_mod",
            )
            node = parse(
                '(footprint "Original" (layer "F.Cu") (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")) (pad "2" smd rect (at 2 0) (size 1 1) (layers "F.Cu")))'
            )
            for name, offset in models or []:
                path = (
                    "${MYCO_PARTS_DIR}/../" + folder + "/" + name
                    if not name.startswith("${")
                    else name
                )
                node.append(
                    [
                        "model",
                        Q(path),
                        ["offset", ["xyz", *map(str, offset)]],
                        ["scale", ["xyz", "1", "1", "1"]],
                        ["rotate", ["xyz", "10", "20", "30"]],
                    ]
                )
                if not name.startswith("${"):
                    self.write(folder + "/" + name, ("original " + name).encode())
            self.write(row["FootprintFile"], dump(node))
        if not shared:
            self.write(
                folder + "/component.json",
                json_bytes(dict(version=1, partID=row["ID"], libraryID=self.lib.id)),
            )
            self.write(folder + "/recipes.json", json_bytes(dict(version=1, items=[])))
        self.write("appdata/components.csv", csv_bytes([row]))
        for name, payload in self.lib.compiled([row]).items():
            self.write(name, payload)
        return row

    def edit(self, row):
        session = ImportSession()
        self.addCleanup(session.close)
        return session, session.load_existing(self.lib, row["ID"])["draft"]

    def save(self, session, draft):
        prepared = session.prepare(self.lib, draft)
        return session.commit(self.lib, prepared["token"], replace=True)

    def test_metadata_edit_preserves_complete_model_assembly(self):
        row = self.component(
            models=[
                ("body.step", [1, 2, 3]),
                ("shell.step", [4, 5, 6]),
                ("${KICAD10_3DMODEL_DIR}/missing.wrl", [0, 0, 0]),
            ]
        )
        original = children(
            parse((self.lib.root / row["FootprintFile"]).read_text()), "model"
        )
        session, draft = self.edit(row)
        draft["part"]["Notes"] = "Metadata only"
        saved = self.save(session, draft)
        result = children(
            parse((self.lib.root / saved["FootprintFile"]).read_text()), "model"
        )
        self.assertEqual(result, original)
        self.assertEqual(
            (self.lib.root / row["AssetFolder"] / "shell.step").read_bytes(),
            b"original shell.step",
        )

    def test_folder_move_rewrites_all_local_models_preserving_transforms(self):
        row = self.component(
            models=[
                ("body.step", [1, 2, 3]),
                ("shell.wrl", [4, 5, 6]),
                ("${KICAD10_3DMODEL_DIR}/missing.step", [7, 8, 9]),
            ]
        )
        before = children(
            parse((self.lib.root / row["FootprintFile"]).read_text()), "model"
        )
        session, draft = self.edit(row)
        draft["category"] = "components/connectors/moved"
        saved = self.save(session, draft)
        after = children(
            parse((self.lib.root / saved["FootprintFile"]).read_text()), "model"
        )
        self.assertEqual([node[2:] for node in after], [node[2:] for node in before])
        self.assertEqual(after[2][1], before[2][1])
        self.assertIn(saved["AssetFolder"], after[0][1])
        self.assertIn(saved["AssetFolder"], after[1][1])
        self.assertEqual(
            (self.lib.root / saved["AssetFolder"] / "shell.wrl").read_bytes(),
            b"original shell.wrl",
        )

    def test_wrl_is_not_uploaded_as_step_and_only_viewed_step_alignment_changes(self):
        row = self.component(
            models=[("shell.wrl", [1, 2, 3]), ("body.step", [4, 5, 6])]
        )
        before = children(
            parse((self.lib.root / row["FootprintFile"]).read_text()), "model"
        )
        session, draft = self.edit(row)
        self.assertEqual(draft["modelIndex"], 1)
        self.assertEqual(
            session.asset(draft["modelAsset"], [".step"])["path"].read_bytes(),
            b"original body.step",
        )
        draft["transform"]["offset"][2] += 0.5
        saved = self.save(session, draft)
        after = children(
            parse((self.lib.root / saved["FootprintFile"]).read_text()), "model"
        )
        self.assertEqual(after[0], before[0])
        self.assertEqual(
            cad.footprint_data((self.lib.root / saved["FootprintFile"]).read_text())[
                "models"
            ][1]["offset"],
            [4, 5, 6.5],
        )

    def test_unresolved_model_reference_survives_without_selected_asset(self):
        row = self.component(models=[("${KICAD10_3DMODEL_DIR}/missing.wrl", [1, 2, 3])])
        before = children(
            parse((self.lib.root / row["FootprintFile"]).read_text()), "model"
        )
        session, draft = self.edit(row)
        self.assertNotIn("modelAsset", draft)
        draft["transform"] = dict(offset=[0, 0, 0], rotate=[0, 0, 0], scale=[1, 1, 1])
        saved = self.save(session, draft)
        self.assertEqual(
            children(
                parse((self.lib.root / saved["FootprintFile"]).read_text()), "model"
            ),
            before,
        )

    def test_explicit_model_removal_is_respected(self):
        row = self.component(
            models=[("body.step", [1, 2, 3]), ("shell.step", [4, 5, 6])]
        )
        session, draft = self.edit(row)
        draft.update(modelAction="remove", modelAsset="")
        saved = self.save(session, draft)
        self.assertEqual(
            cad.footprint_data((self.lib.root / saved["FootprintFile"]).read_text())[
                "models"
            ],
            [],
        )

    def test_legacy_shared_passive_keeps_cad_and_flat_catalog_on_metadata_edit(self):
        row = self.component(shared=True, models=[("body.step", [1, 2, 3])])
        originals = {
            field: (self.lib.root / row[field]).read_bytes()
            for field in ("SymbolFile", "FootprintFile")
        }
        session, draft = self.edit(row)
        draft["part"]["Description"] = "Edited metadata"
        saved = self.save(session, draft)
        self.assertEqual(saved["AssetFolder"], "")
        for field, original in originals.items():
            self.assertEqual(saved[field], row[field])
            self.assertEqual((self.lib.root / saved[field]).read_bytes(), original)

    def test_legacy_shared_spec_edits_are_validated_without_replacing_cad(self):
        row = self.component(shared=True)
        session, draft = self.edit(row)
        draft["part"]["Value"] = "4k7"
        saved = self.save(session, draft)
        self.assertEqual(saved["Value"], "4.7k")
        self.assertEqual(saved["SymbolFile"], row["SymbolFile"])
        self.assertEqual(saved["FootprintFile"], row["FootprintFile"])
        session, draft = self.edit(saved)
        draft["part"]["Tolerance"] = "-1%"
        with self.assertRaises(ValueError):
            session.prepare(self.lib, draft)

    def test_legacy_shared_passive_changes_to_bundled_models_when_package_changes(self):
        row = self.component(shared=True)
        session, draft = self.edit(row)
        draft["part"]["Package"] = "0603"
        saved = self.save(session, draft)
        self.assertEqual(saved["AssetFolder"], "")
        self.assertNotIn("legacy", saved["FootprintFile"])
        self.assertIn("0603", saved["FootprintFile"])

    def test_symbol_only_metadata_edit_preserves_symbol_without_inventing_footprint(
        self,
    ):
        row = self.component(footprint=False)
        before = (self.lib.root / row["SymbolFile"]).read_bytes()
        session, draft = self.edit(row)
        draft["part"]["Type"] = "other"
        draft["part"]["Notes"] = "Missing footprint kept explicit"
        draft["transform"] = dict(offset=[0, 0, 0], rotate=[0, 0, 0], scale=[1, 1, 1])
        saved = self.save(session, draft)
        self.assertEqual(saved["FootprintFile"], "")
        self.assertEqual((self.lib.root / saved["SymbolFile"]).read_bytes(), before)

    def test_footprint_only_metadata_edit_preserves_pads_and_links(self):
        row = self.component(symbol=False)
        before = (self.lib.root / row["FootprintFile"]).read_bytes()
        session, draft = self.edit(row)
        draft["part"]["Notes"] = "Missing symbol kept explicit"
        saved = self.save(session, draft)
        self.assertEqual(saved["SymbolFile"], "")
        self.assertEqual((self.lib.root / saved["FootprintFile"]).read_bytes(), before)

    def test_existing_pin_mismatch_allows_metadata_accessory_and_alignment_edits_only(
        self,
    ):
        row = self.component(models=[("body.step", [1, 2, 3])])
        path = self.lib.root / row["FootprintFile"]
        node = parse(path.read_text())
        node.append(parse('(pad "MP" smd rect (at 4 0) (size 1 1) (layers "F.Cu"))'))
        path.write_text(dump(node))
        before_pads = children(node, "pad")
        session, draft = self.edit(row)
        draft["part"]["Notes"] = "Keep existing mechanical tab"
        draft["transform"]["offset"][2] += 0.5
        draft["recipe"] = {
            "items": [{"manufacturer": "Fixture", "mpn": "Housing", "quantity": 1}]
        }
        review = session.prepare(self.lib, draft)
        self.assertTrue(
            any("mismatch preserved" in warning for warning in review["warnings"])
        )
        saved = session.commit(self.lib, review["token"], replace=True)
        result = (self.lib.root / saved["FootprintFile"]).read_text()
        self.assertEqual(children(parse(result), "pad"), before_pads)
        self.assertEqual(cad.footprint_data(result)["models"][0]["offset"], [1, 2, 3.5])
        self.assertEqual(self.lib.recipe(saved)["items"][0]["quantity"], 1)
        changed, draft = self.edit(saved)
        changed.upload("replacement.kicad_mod", result.encode())
        draft["footprintAsset"] = next(
            item["id"]
            for item in changed.inventory()["assets"]
            if item["label"] == "replacement.kicad_mod"
        )
        with self.assertRaisesRegex(ValueError, "pin numbers differ"):
            changed.prepare(self.lib, draft)

    def test_existing_blank_manufacturer_can_remain_blank_but_new_parts_require_it(
        self,
    ):
        row = self.component()
        row["Manufacturer"] = ""
        self.write("appdata/components.csv", csv_bytes([row]))
        session, draft = self.edit(row)
        draft["part"]["Notes"] = "Preserve unknown manufacturer"
        review = session.prepare(self.lib, draft)
        self.assertTrue(
            any("no manufacturer" in warning for warning in review["warnings"])
        )
        saved = session.commit(self.lib, review["token"], replace=True)
        self.assertEqual(saved["Manufacturer"], "")
        fresh = ImportSession()
        self.addCleanup(fresh.close)
        with self.assertRaisesRegex(ValueError, "Manufacturer is required"):
            fresh.prepare(
                self.lib,
                {
                    "mode": "accessory",
                    "category": "components/accessories",
                    "part": {"Type": "accessory", "MPN": "NEW"},
                },
            )
        session, draft = self.edit(saved)
        draft["recipe"] = {
            "items": [{"manufacturer": "", "mpn": "Housing", "quantity": 1}]
        }
        with self.assertRaisesRegex(ValueError, "manufacturer and part number"):
            session.prepare(self.lib, draft)

    def test_existing_non_url_reference_survives_metadata_edit_but_changes_validate(
        self,
    ):
        row = self.component()
        row["Datasheet"] = "PART"
        self.write("appdata/components.csv", csv_bytes([row]))
        session, draft = self.edit(row)
        draft["part"]["Notes"] = "Keep original reference"
        review = session.prepare(self.lib, draft)
        self.assertTrue(any("not an online URL" in item for item in review["warnings"]))
        saved = session.commit(self.lib, review["token"], replace=True)
        self.assertEqual(saved["Datasheet"], "PART")
        session, draft = self.edit(saved)
        draft["part"]["Datasheet"] = "OTHER-PART"
        with self.assertRaisesRegex(ValueError, "Datasheet must be an online URL"):
            session.prepare(self.lib, draft)
        draft["part"]["Datasheet"] = "https://example.com/part.pdf"
        saved = self.save(session, draft)
        self.assertEqual(saved["Datasheet"], "https://example.com/part.pdf")

    def test_migrated_item_names_and_private_filenames_stay_stable_on_edit_and_move(
        self,
    ):
        row = self.component(models=[("body.step", [1, 2, 3])])
        original_path = self.lib.root / row["FootprintFile"]
        node = parse(original_path.read_text())
        node[1] = Q("OffsetFootprint")
        original_path.unlink()
        row["Footprint"] = "fixture:OffsetFootprint"
        row["FootprintFile"] = (
            row["AssetFolder"] + "/footprint.pretty/OffsetFootprint.kicad_mod"
        )
        self.write(row["FootprintFile"], dump(node))
        self.write("appdata/components.csv", csv_bytes([row]))
        links = {
            field: row[field]
            for field in ("Symbol", "Footprint", "SymbolFile", "FootprintFile")
        }
        session, draft = self.edit(row)
        draft["part"]["Notes"] = "Keep existing KiCad item identities"
        draft["transform"]["offset"][2] += 0.5
        saved = self.save(session, draft)
        self.assertEqual({field: saved[field] for field in links}, links)
        self.assertEqual(
            cad.footprint_data((self.lib.root / saved["FootprintFile"]).read_text())[
                "name"
            ],
            "OffsetFootprint",
        )
        self.assertEqual(
            cad.symbols((self.lib.root / saved["SymbolFile"]).read_text()), ["Original"]
        )
        session, draft = self.edit(saved)
        draft["category"] = "components/connectors/reorganized"
        moved = self.save(session, draft)
        self.assertEqual(moved["Symbol"], links["Symbol"])
        self.assertEqual(moved["Footprint"], links["Footprint"])
        for field in ("SymbolFile", "FootprintFile"):
            self.assertEqual(
                moved[field],
                moved["AssetFolder"] + links[field][len(row["AssetFolder"]) :],
            )
            self.assertTrue((self.lib.root / moved[field]).is_file())


if __name__ == "__main__":
    unittest.main()
