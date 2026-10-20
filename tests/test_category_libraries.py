"""Folder-based chooser grouping, compatibility and transactional projections."""
import copy
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import test_core
from manager import cad, kicad
from manager.category_libraries import category_label, INDEX
from manager.sexpr import children, parse, value
from manager.storage import APPDATA, csv_bytes, digest


class CategoryLibraryTests(unittest.TestCase):
    setUp = test_core.LibraryCase.setUp
    session = test_core.LibraryCase.session
    connector = test_core.LibraryCase.connector

    def save(self, mpn="HDR-3", category="components/connectors"):
        session, draft = self.connector()
        draft["part"]["MPN"] = mpn
        draft["category"] = category
        return session.commit(self.lib, session.prepare(self.lib, draft)["token"])

    def entries(self, writes=None):
        text = ((writes or {}).get(APPDATA + "/fp-lib-table") or (self.lib.appdata / "fp-lib-table").read_bytes()).decode()
        return {str(value(e, "name")): e for e in children(parse(text), "lib")}

    def generated(self, row):
        with sqlite3.connect(self.lib.appdata / "parts.sqlite") as db:
            ref = db.execute("SELECT KiCadFootprint FROM components WHERE ID=?", (row["ID"],)).fetchone()[0]
        db.close()
        nick, name = ref.split(":", 1)
        uri = value(self.entries()[nick], "uri")
        return self.lib.appdata / uri.removeprefix("${MYCO_PARTS_DIR}/") / (name + ".kicad_mod")

    def test_folder_names(self):
        for folder, name in {
            "components/ICs": "Virtus - IC",
            "components/connectors": "Virtus - Connectors",
            "components/connectors/deutsch connectors": "Virtus - Deutsch Connectors",
            "components/connectors/deutsch": "Virtus - Deutsch Connectors",
            "components/ICs/op amps": "Virtus - IC - Op Amps",
            "components": "Virtus - Components",
        }.items():
            self.assertEqual(category_label(folder), name)

    def test_grouping_native_render_and_unchanged_authority(self):
        a = self.save()
        b = self.save("HDR-OTHER")
        source = (self.lib.root / a["FootprintFile"]).read_bytes()
        entries = self.entries()
        self.assertEqual([n for n, e in entries.items() if not children(e, "hidden")], ["Virtus - Connectors"])
        self.assertTrue(children(entries[a["Footprint"].split(":")[0]], "hidden"))
        self.assertFalse(children(entries[a["Footprint"].split(":")[0]], "disabled"))
        self.assertEqual(self.generated(a).parent, self.generated(b).parent)
        self.assertEqual(parse(source.decode())[2:], parse(self.generated(a).read_text())[2:])
        self.assertEqual((self.lib.root / a["FootprintFile"]).read_bytes(), source)
        config = json.loads((self.lib.appdata / "parts.kicad_dbl").read_text())
        self.assertEqual(config["libraries"][0]["name"], "Virtus - Connectors")
        self.assertEqual(config["libraries"][0]["footprints"], "KiCadFootprint")
        self.assertTrue(config["globally_unique_keys"])
        with sqlite3.connect(self.lib.appdata / "parts.sqlite") as db:
            self.assertEqual(db.execute("SELECT Footprint FROM components WHERE ID=?", (a["ID"],)).fetchone()[0], a["Footprint"])
        db.close()
        if kicad.cli_path():
            self.assertEqual(len(kicad.render("fp", self.generated(a).parent)), 2)

    def test_collision_keeps_previously_allocated_item_names(self):
        a = self.save()
        rows = self.lib.rows()
        b = dict(a, ID="second-id", Manufacturer="Another", Footprint="other-source:HDR-3")
        rows.append(b)
        first = self.generated(a)
        writes = self.lib.compiled(rows)
        self.lib.transaction({APPDATA + "/components.csv": csv_bytes(rows), **writes})
        self.assertEqual(first, self.generated(a))
        self.assertNotEqual(first, self.generated(b))
        left = self.lib.compiled(list(reversed(rows)))
        right = self.lib.compiled(rows)
        for key in (APPDATA + "/parts.sqlite", APPDATA + "/fp-lib-table", APPDATA + "/sym-lib-table"):
            left.pop(key)
            right.pop(key)
        self.assertEqual(left, right)

    def test_move_preserves_old_alias_and_model_transform(self):
        a = self.save()
        old_alias = self.generated(a)
        before = cad.footprint_data(old_alias.read_text())
        old = self.lib.root / a["AssetFolder"]
        destination = self.lib.root / "components/connectors/deutsch/renamed"
        destination.parent.mkdir(parents=True)
        old.rename(destination)
        self.assertEqual(self.lib.reconcile_folders(), [])
        moved = self.lib.rows()[0]
        new_alias = self.generated(moved)
        self.assertNotEqual(old_alias.parent, new_alias.parent)
        self.assertTrue(old_alias.exists())
        self.assertTrue(children(self.entries()["Virtus - Connectors"], "hidden"))
        self.assertEqual(self.lib.rows()[0]["Footprint"], a["Footprint"])
        after = cad.footprint_data(new_alias.read_text())
        for key in ("offset", "rotate", "scale"):
            self.assertEqual(before["models"][0][key], after["models"][0][key])
        self.assertIn("/deutsch/renamed/", after["models"][0]["path"])
        self.assertEqual(parse(old_alias.read_text()), parse(new_alias.read_text()))

    def test_projection_rollback_and_deleted_source_cleanup(self):
        a = self.save()
        projection = self.generated(a)
        before = {p.relative_to(self.lib.root).as_posix(): p.read_bytes() for p in self.lib.root.rglob("*") if p.is_file() and "backups" not in p.parts}
        writes = self.lib.compiled([])
        writes[APPDATA + "/components.csv"] = csv_bytes([])
        replace = self.lib._replace
        failed = False
        def fail(path, data):
            nonlocal failed
            if path.name == "category-libraries.json" and not failed:
                failed = True
                raise OSError("injected category failure")
            return replace(path, data)
        with patch.object(self.lib, "_replace", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                self.lib.transaction(writes)
        for name, data in before.items():
            self.assertEqual((self.lib.root / name).read_bytes(), data, name)
        self.lib.transaction(writes)
        self.assertFalse(projection.exists())
        self.assertNotIn("Virtus - Connectors", self.entries())

    def test_other_component_cad_changes_invalidate_preparation(self):
        a = self.save()
        session, draft = self.connector()
        draft["part"]["MPN"] = "NEW"
        prepared = session.prepare(self.lib, draft)
        path = self.lib.root / a["FootprintFile"]
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "file changed since review"):
            session.commit(self.lib, prepared["token"])
        self.assertEqual(len(self.lib.rows()), 1)

    def test_label_collision_logos_and_relative_models(self):
        a = self.save(category="components/ICs")
        rows = self.lib.rows() + [dict(a, ID="another", Category="components/IC")]
        pretty = self.lib.root / "components/logos/Test.pretty"
        pretty.mkdir()
        (pretty / "Mark.kicad_mod").write_text(test_core.FOOTPRINT)
        writes = self.lib.compiled(rows)
        entries = self.entries(writes)
        visible = [n for n, e in entries.items() if not children(e, "hidden")]
        self.assertEqual(len(visible), 3)
        self.assertIn("Virtus - Logos", visible)
        index = json.loads(writes[INDEX])
        self.assertNotEqual(index["categories"]["components/IC"]["name"], index["categories"]["components/ICs"]["name"])
        logo = next(data for name, data in writes.items() if name.endswith("/Mark.kicad_mod"))
        self.assertIn("${MYCO_PARTS_DIR}/../components/logos/Test.pretty/supplier.step", logo.decode())

    def test_legacy_module_projects_without_upgrading_working_cad(self):
        a = self.save()
        file = self.lib.root / a["FootprintFile"]
        legacy = file.read_text().replace("(footprint ", "(module ", 1)
        file.write_text(legacy)
        writes = self.lib.compiled(self.lib.rows())
        self.lib.transaction(writes)
        self.assertEqual(file.read_text(), legacy)
        self.assertEqual(parse(self.generated(a).read_text())[0], "module")
        if kicad.cli_path():
            self.assertEqual(len(kicad.render("fp", self.generated(a).parent)), 1)
