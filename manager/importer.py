"""Immutable upload sessions, import review, and all-or-nothing component saves."""

from __future__ import annotations

import copy
import io
import json
import re
from pathlib import Path
import stat
import tempfile
import uuid
import zipfile

from . import cad, standard_packages
from .storage import (
    APPDATA,
    COLUMNS,
    inside,
    relative,
    category_path,
    slug,
    digest,
    timestamp,
    json_bytes,
    csv_bytes,
)

MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 10000


class ImportSession:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.temp = tempfile.TemporaryDirectory(prefix="library-import-")
        self.root = Path(self.temp.name)
        self.assets = {}
        self.originals = {}
        self.prepared = None
        self.total = 0
        self.warnings = []
        self.existing_fingerprints = {}
        self.edit_baseline = None

    def close(self):
        self.temp.cleanup()

    def load_existing(self, lib, ident):
        row = next((r for r in lib.rows() if r["ID"] == ident), None)
        if not row:
            raise ValueError("Component no longer exists")
        mode = (
            "generic"
            if row["SymbolFile"].startswith("components/generic_models/")
            and row["FootprintFile"].startswith("components/generic_models/")
            else "bespoke"
            if row["Symbol"] or row["Footprint"]
            else "accessory"
        )
        draft = dict(
            editingID=ident,
            part=row,
            mode=mode,
            category=row["Category"],
            folderName=Path(row["AssetFolder"]).name,
            recipe=lib.recipe(row),
            alternative=False,
            layout="single",
            pinsConfirmed=False,
            modelAction="preserve",
            modelIndex=None,
        )
        for field in ("SymbolFile", "FootprintFile"):
            if row[field]:
                path = inside(lib.root, row[field])
                self.existing_fingerprints[row[field]] = digest(path.read_bytes())
        if mode == "bespoke":
            for field, key in [
                ("SymbolFile", "symbolAsset"),
                ("FootprintFile", "footprintAsset"),
            ]:
                if not row[field] or (
                    field == "SymbolFile"
                    and row[field].startswith("components/generic_models/")
                    and row["Type"] in ("resistor", "capacitor")
                ):
                    continue
                path = inside(lib.root, row[field])
                name = "current/" + path.name
                self.upload(name, path.read_bytes())
                draft[key] = digest(name.encode())[:24]
            draft["symbolName"] = (
                row["Symbol"].split(":", 1)[1] if row["Symbol"] else ""
            )
            if row["FootprintFile"]:
                fp = cad.footprint_data(
                    inside(lib.root, row["FootprintFile"]).read_text()
                )
                for index, model in enumerate(fp["models"]):
                    prefix = "${MYCO_PARTS_DIR}/../"
                    if not model["path"].startswith(prefix):
                        continue
                    model_relative = model["path"][len(prefix) :]
                    path = inside(lib.root, model_relative)
                    if not path.is_file():
                        continue
                    self.existing_fingerprints[model_relative] = digest(
                        path.read_bytes()
                    )
                    if path.suffix.lower() not in (".step", ".stp") or draft.get(
                        "modelAsset"
                    ):
                        continue
                    name = "current/model" + path.suffix.lower()
                    self.upload(name, path.read_bytes())
                    draft["modelAsset"] = digest(name.encode())[:24]
                    draft["modelIndex"] = index
                    draft["transform"] = {
                        k: model[k] for k in ("offset", "rotate", "scale")
                    }
            # The original library files are backed up independently of new uploads.
            self.originals = {}
        self.edit_baseline = copy.deepcopy(draft)
        return dict(inventory=self.inventory(), draft=draft)

    def upload(self, name, data):
        name = relative(name)
        if name in self.originals:
            if self.originals[name] == data:
                return
            raise ValueError(
                "Different uploads have the same relative filename: " + name
            )
        if self.total + len(data) > MAX_BYTES or len(self.originals) >= MAX_FILES:
            raise ValueError("Import is limited to 512 MiB and 10,000 files")
        # Work in a scratch copy until the entire archive has passed validation.
        additions = {}
        budget = [self.total + len(data), len(self.assets)]

        def expand(label, payload, depth):
            if label.lower().endswith(".zip"):
                if depth > 3:
                    raise ValueError("ZIP nesting exceeds three levels")
                with zipfile.ZipFile(io.BytesIO(payload)) as z:
                    for entry in z.infolist():
                        path = relative(entry.filename)
                        if entry.is_dir():
                            continue
                        if (
                            stat.S_ISLNK(entry.external_attr >> 16)
                            or entry.flag_bits & 1
                        ):
                            raise ValueError(
                                "Symlink and encrypted ZIP members are unsupported"
                            )
                        if any(
                            p.startswith(".") or p == "__MACOSX"
                            for p in Path(path).parts
                        ):
                            continue
                        budget[0] += entry.file_size
                        budget[1] += 1
                        if budget[0] > MAX_BYTES or budget[1] > MAX_FILES:
                            raise ValueError("Expanded ZIP exceeds import limits")
                        expand(label + "!/" + path, z.read(entry), depth + 1)
            elif Path(label).suffix.lower() in (
                ".kicad_sym",
                ".kicad_mod",
                ".step",
                ".stp",
            ):
                if label in additions:
                    raise ValueError("Duplicate ZIP member: " + label)
                additions[label] = payload

        expand(name, data, 0)
        for label, payload in additions.items():
            key = digest(label.encode())[:24]
            path = self.root / (key + Path(label).suffix.lower())
            path.write_bytes(payload)
            self.assets[key] = dict(
                id=key,
                label=label,
                path=path,
                sha256=digest(payload),
                size=len(payload),
            )
        self.originals[name] = data
        self.total = budget[0]
        self.prepared = None

    def asset(self, key, extensions):
        if key not in self.assets:
            raise ValueError("Select an uploaded asset")
        item = self.assets[key]
        if item["path"].suffix.lower() not in extensions:
            raise ValueError("Unexpected asset type")
        if digest(item["path"].read_bytes()) != item["sha256"]:
            raise ValueError("Uploaded file changed after review")
        return item

    def inventory(self):
        items = []
        for item in self.assets.values():
            entry = {k: v for k, v in item.items() if k != "path"}
            entry["type"] = item["path"].suffix.lower()
            try:
                if entry["type"] == ".kicad_sym":
                    text = item["path"].read_text()
                    entry["symbols"] = cad.symbols(text)
                    leaves = cad.symbol_choices(text)
                    entry["suggestedSymbol"] = leaves[0] if len(leaves) == 1 else ""
                    definitions = {
                        str(n[1]): n for n in cad.children(cad.parse(text), "symbol")
                    }
                    entry["metadata"] = {
                        name: cad.symbol_metadata(
                            cad.flatten_symbol(text, name), definitions[name]
                        )
                        for name in entry["symbols"]
                    }
                if entry["type"] == ".kicad_mod":
                    entry["footprint"] = cad.footprint_data(item["path"].read_text())
            except (ValueError, UnicodeError) as exc:
                entry["error"] = str(exc)
            items.append(entry)
        return dict(
            id=self.id,
            assets=items,
            standardPackages=standard_packages.inventory(),
            originalCount=len(self.originals),
            warnings=self.warnings,
        )

    def archive(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
            manifest = []
            for name, data in self.originals.items():
                target = "originals/" + name
                z.writestr(target, data)
                manifest.append(dict(path=target, sha256=digest(data), bytes=len(data)))
            z.writestr("manifest.json", json_bytes(dict(version=1, files=manifest)))
        return stream.getvalue()

    def inspect(self, draft):
        pins = []
        footprint = None
        original = None
        if draft.get("symbolAsset"):
            original = cad.flatten_symbol(
                self.asset(draft["symbolAsset"], [".kicad_sym"])["path"].read_text(),
                draft.get("symbolName", ""),
            )
            pins = cad.symbol_pins(original)
        if draft.get("footprintAsset"):
            footprint = cad.footprint_data(
                self.asset(draft["footprintAsset"], [".kicad_mod"])["path"].read_text()
            )
        return dict(
            pins=pins,
            footprint=footprint,
            inference=cad.infer_connector(footprint, pins) if footprint else None,
        ), original

    def preview(self, draft, kind="symbol"):
        """Render draft CAD in scratch space, independently of save validation."""
        from . import kicad

        info, original = self.inspect(draft)
        if kind == "footprint":
            source = self.asset(draft.get("footprintAsset"), [".kicad_mod"])
            text = source["path"].read_text()
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                pretty = Path(directory) / "preview.pretty"
                pretty.mkdir()
                (pretty / (cad.footprint_data(text)["name"] + ".kicad_mod")).write_text(
                    text
                )
                return dict(svgs=kicad.render("fp", pretty))
        proposed = original
        if draft.get("alternative"):
            inference = info["inference"]
            if not inference or not inference["eligible"]:
                raise ValueError(
                    "Select compatible connector files to preview alternate body styles"
                )
            proposed = cad.connector_body_styles(
                inference["count"],
                draft.get("layout", "single"),
                info["pins"],
                "Preview",
            )
        if proposed is None:
            raise ValueError("Select a symbol library and symbol")
        metadata = draft.get("part", {})
        properties = {
            key: metadata[key]
            for key in ("Value", "Reference", "Datasheet")
            if metadata.get(key)
        }
        if metadata.get("MPN") and not properties.get("Value"):
            properties["Value"] = metadata["MPN"]

        def render(node, props=None):
            # Render each style explicitly: CLI exports vary across KiCad versions.
            styles = sorted(
                {
                    int(str(u[1]).rsplit("_", 1)[-1])
                    for u in cad.children(node, "symbol")
                    if str(u[1]).rsplit("_", 1)[-1].isdigit()
                }
                - {0}
            ) or [1]
            svgs = []
            for style in styles:
                selected = copy.deepcopy(node)
                selected[:] = [
                    n
                    for n in selected
                    if not (
                        isinstance(n, list)
                        and n
                        and n[0] == "symbol"
                        and str(n[1]).rsplit("_", 1)[-1] not in ("0", str(style))
                    )
                ]
                for unit in cad.children(selected, "symbol"):
                    if str(unit[1]).endswith("_" + str(style)):
                        unit[1] = cad.Q(str(unit[1]).rsplit("_", 1)[0] + "_1")
                text = cad.symbol_library(selected, str(selected[1]), props)
                cache = getattr(self, "render_cache", {})
                key = digest(text.encode())
                if key not in cache:
                    path = self.root / "live-symbol.kicad_sym"
                    path.write_text(text)
                    if len(cache) > 24:
                        cache.clear()
                    cache[key] = kicad.render("sym", path, str(selected[1]))
                    self.render_cache = cache
                svgs.extend(cache[key])
            return svgs

        return dict(
            svgs=render(proposed, properties),
            originals=render(original)
            if draft.get("alternative") and original is not None
            else [],
            info=dict(info, proposedPins=cad.symbol_pins(proposed)),
        )

    def prepare(self, lib, draft):
        if getattr(self, "library_id", lib.id) != lib.id:
            raise ValueError(
                "The selected library changed. Reopen this import in the intended library."
            )
        issues = lib.reconcile_folders()
        if issues:
            raise ValueError(
                "Resolve component folder issues before saving: " + "; ".join(issues)
            )
        revision = lib.revision()
        rows = lib.rows()
        if revision != lib.revision():
            raise ValueError("The library changed while reading the catalog; reload")
        for name, sha in self.existing_fingerprints.items():
            if digest(inside(lib.root, name).read_bytes()) != sha:
                raise ValueError(
                    "The edited component changed outside the manager. Reopen it before saving."
                )
        metadata = draft.get("part", {})
        row = {c: str(metadata.get(c, "")).strip() for c in COLUMNS}
        editing_record = next(
            (r for r in rows if r["ID"] == draft.get("editingID")), None
        )
        preserve_blank_manufacturer = bool(
            editing_record
            and not editing_record["Manufacturer"]
            and not row["Manufacturer"]
        )
        for field in ("MPN", "Manufacturer", "Type"):
            if not row[field] and not (
                field == "Manufacturer" and preserve_blank_manufacturer
            ):
                raise ValueError(field + " is required")
        if row["Type"] not in (
            "resistor",
            "capacitor",
            "connector",
            "IC",
            "other",
            "accessory",
        ):
            raise ValueError("Choose a supported component type")
        mode = draft.get("mode", "bespoke")
        if mode not in ("generic", "bespoke", "accessory"):
            raise ValueError("Choose an import mode")
        if (mode == "accessory" or row["Type"] == "accessory") and not editing_record:
            raise ValueError("Add accessories inside their owning component")
        if row["Type"] == "connector":
            for field, unit in (("Current_A", "A"), ("Voltage_V", "V")):
                if row[field]:
                    match = re.fullmatch(
                        r"(\d+(?:\.\d*)?|\.\d+)\s*" + unit + r"?", row[field], re.I
                    )
                    if not match or float(match[1]) <= 0:
                        raise ValueError(f"{field} must be a positive rating in {unit}")
                    row[field] = match[1]
        existing = next(
            (
                r
                for r in rows
                if r["Manufacturer"].casefold() == row["Manufacturer"].casefold()
                and r["MPN"].casefold() == row["MPN"].casefold()
            ),
            None,
        )
        if draft.get("editingID"):
            existing = next((r for r in rows if r["ID"] == draft["editingID"]), None)
            if existing is None:
                raise ValueError("Edited part no longer exists")
        row["ID"] = existing["ID"] if existing else self._new_id(row, rows)
        if any(
            r["ID"] != row["ID"]
            and (r["Manufacturer"].casefold(), r["MPN"].casefold())
            == (row["Manufacturer"].casefold(), row["MPN"].casefold())
            for r in rows
        ):
            raise ValueError("Another part already has this manufacturer and MPN")
        category = category_path(
            draft.get("category")
            or (
                "components/connectors"
                if row["Type"] == "connector"
                else "components/ICs"
            )
        )
        if mode == "generic":
            category = "components/" + row["Type"] + "s"
        for part in Path(category).parts:
            slug(part)
        # Category directories cannot descend into another component's private folder.
        for other in rows:
            if other["AssetFolder"] and (
                category == other["AssetFolder"]
                or category.startswith(other["AssetFolder"] + "/")
            ):
                raise ValueError(
                    "Choose a category folder, not an existing component folder"
                )
        folder = ""
        if mode == "bespoke":
            folder = (
                existing["AssetFolder"]
                if existing
                and existing["AssetFolder"]
                and existing["Category"] == category
                else category + "/" + slug(draft.get("folderName") or row["MPN"])
            )
            if any(
                r["ID"] != row["ID"]
                and r["AssetFolder"].casefold() == folder.casefold()
                for r in rows
            ):
                folder = category + "/" + slug(row["Manufacturer"] + " " + row["MPN"])
            if any(
                r["ID"] != row["ID"]
                and r["AssetFolder"].casefold() == folder.casefold()
                for r in rows
            ):
                raise ValueError("Component folder already belongs to another part")
            target = inside(lib.root, folder)
            if target.exists() and (not existing or folder != existing["AssetFolder"]):
                raise ValueError(
                    "Destination component folder already exists; choose another folder name"
                )
        row["Category"] = category
        row["AssetFolder"] = folder
        row["Status"] = ""
        if mode == "generic" and not row["Package"]:
            row["Package"] = "0805"
        row["Value"] = row["Value"] or row["MPN"]
        row["Reference"] = row["Reference"] or {
            "resistor": "R",
            "capacitor": "C",
            "connector": "J",
            "IC": "U",
        }.get(row["Type"], "U")
        row["CreatedUTC"] = existing["CreatedUTC"] if existing else timestamp()
        row["UpdatedUTC"] = timestamp()
        warnings = []
        for field in ("Datasheet", "SupplierURL"):
            if row[field] and not row[field].startswith(("https://", "http://")):
                if (
                    self.edit_baseline
                    and editing_record
                    and self.edit_baseline["editingID"] == editing_record["ID"]
                    and row[field] == editing_record[field]
                ):
                    warnings.append(
                        f"The existing {field} value is not an online URL. It was preserved; replace it with a verified link when known."
                    )
                else:
                    raise ValueError(field + " must be an online URL")
        writes = standard_packages.template_writes(self, lib, draft.get("footprintAsset", ""))
        deletes = []
        if preserve_blank_manufacturer:
            warnings.append(
                "The existing record has no manufacturer. That blank value was preserved; add the manufacturer when known."
            )
        info = {}
        symbol_text = None
        footprint_text = None
        if existing and existing["AssetFolder"] and existing["AssetFolder"] != folder:
            previous = inside(lib.root, existing["AssetFolder"])
            for path in previous.rglob("*"):
                if path.is_symlink():
                    raise ValueError(
                        "Cannot move a component folder containing symlinks"
                    )
                if path.is_file():
                    archive_folder = folder or (
                        APPDATA
                        + "/replaced-assets/"
                        + slug(row["ID"])
                        + "-"
                        + uuid.uuid4().hex[:8]
                    )
                    writes[
                        archive_folder + "/" + path.relative_to(previous).as_posix()
                    ] = path.read_bytes()
                    deletes.append(path.relative_to(lib.root).as_posix())
        nick = lib.prefix + "_" + digest(row["ID"].encode())[:12]
        working_name = slug(row["MPN"])
        baseline = self.edit_baseline
        same_edit = bool(
            baseline and existing and baseline["editingID"] == existing["ID"]
        )
        preserve_shared = bool(
            same_edit
            and mode == "generic"
            and baseline["mode"] == "generic"
            and existing["Type"] == row["Type"]
            and existing["Package"] == str(metadata.get("Package", "")).strip()
            and (
                "/legacy/" in existing["SymbolFile"]
                or "/legacy/" in existing["FootprintFile"]
            )
        )
        preserve_incomplete = bool(
            same_edit
            and mode == "bespoke"
            and baseline["mode"] == "bespoke"
            and (not existing["Symbol"] or not existing["Footprint"])
            and all(
                draft.get(key, "") == baseline.get(key, "")
                for key in ("symbolAsset", "symbolName", "footprintAsset", "modelAsset")
            )
            and not draft.get("alternative")
            and draft.get("modelAction", "preserve") == "preserve"
            and (
                draft.get("transform")
                or dict(offset=[0, 0, 0], rotate=[0, 0, 0], scale=[1, 1, 1])
            )
            == (
                baseline.get("transform")
                or dict(offset=[0, 0, 0], rotate=[0, 0, 0], scale=[1, 1, 1])
            )
        )
        if preserve_shared or preserve_incomplete:
            if preserve_shared:
                row["Package"] = existing["Package"]
                _normalize_changed_passive_specs(row, existing)
            for field in ("Symbol", "Footprint", "SymbolFile", "FootprintFile"):
                row[field] = existing[field]
            moves = (
                {existing["AssetFolder"]: folder}
                if existing["AssetFolder"] and folder != existing["AssetFolder"]
                else {}
            )
            for field in ("SymbolFile", "FootprintFile"):
                if moves and row[field].startswith(existing["AssetFolder"] + "/"):
                    row[field] = folder + row[field][len(existing["AssetFolder"]) :]
            if existing["SymbolFile"]:
                symbol_text = inside(lib.root, existing["SymbolFile"]).read_text()
                info["pins"] = cad.symbol_pins(
                    cad.flatten_symbol(symbol_text, row["Symbol"].split(":", 1)[1])
                )
            if existing["FootprintFile"]:
                footprint_text = inside(lib.root, existing["FootprintFile"]).read_text()
                if moves:
                    footprint_text = cad.footprint_payload(
                        footprint_text,
                        cad.footprint_data(footprint_text)["name"],
                        preserve_models=True,
                        path_moves=moves,
                    )
                    writes[row["FootprintFile"]] = footprint_text.encode()
                info["footprint"] = cad.footprint_data(footprint_text)
                if preserve_shared:
                    prefix = "${MYCO_PARTS_DIR}/../components/generic_models/"
                    for index, model in enumerate(info["footprint"]["models"]):
                        if model["path"].startswith(prefix) and Path(
                            model["path"]
                        ).suffix.lower() in (".step", ".stp"):
                            model_relative = model["path"][
                                len("${MYCO_PARTS_DIR}/../") :
                            ]
                            if inside(lib.root, model_relative).is_file():
                                info["genericModel"] = model["path"][len(prefix) :]
                                info["genericModelIndex"] = index
                                break
            if preserve_incomplete:
                warnings.append(
                    "Existing incomplete CAD links were preserved. Supply the missing symbol or footprint to make this component placeable."
                )
        elif mode == "generic":
            if row["Type"] not in ("resistor", "capacitor"):
                raise ValueError(
                    "Generic passive models support resistors and capacitors"
                )
            from .passives import normalize

            normalize(row, metadata)
            for field in (
                "Value",
                "Package",
                "Tolerance",
                "Power_W" if row["Type"] == "resistor" else "Voltage_VDC",
            ):
                if not row[field]:
                    raise ValueError(field + " is required for a generic passive")
            inventory = json.loads(
                (lib.root / "components/generic_models/inventory.json").read_text()
            )
            template = next(
                (
                    r
                    for r in inventory
                    if r["type"] == row["Type"] and r["package"] == row["Package"]
                ),
                None,
            )
            if not template:
                raise ValueError("Select a bundled package, or use a bespoke footprint")
            row["SymbolFile"] = "components/generic_models/" + template["symbol"]
            row["FootprintFile"] = "components/generic_models/" + template["footprint"]
            row["Symbol"] = (
                lib.prefix + "_" + row["Type"] + ":" + template["symbolName"]
            )
            row["Footprint"] = (
                lib.prefix + "_" + row["Type"] + ":" + Path(template["footprint"]).stem
            )
            symbol_text = inside(lib.root, row["SymbolFile"]).read_text()
            footprint_text = inside(lib.root, row["FootprintFile"]).read_text()
            info = dict(
                pins=cad.symbol_pins(
                    cad.flatten_symbol(symbol_text, template["symbolName"])
                ),
                footprint=cad.footprint_data(footprint_text),
                genericModel=template["model"],
            )
            if self.originals:
                warnings.append(
                    "Uploaded originals will be archived; generic mode uses the selected shared models."
                )
        elif mode == "accessory":
            row.update(Symbol="", Footprint="", SymbolFile="", FootprintFile="")
        else:
            info, original = self.inspect(draft)
            passive_template = None
            if row["Type"] in ("resistor", "capacitor") and (
                not info["footprint"] or original is None
            ):
                from .passives import normalize

                normalize(row, metadata)
                inventory = json.loads(
                    (lib.root / "components/generic_models/inventory.json").read_text()
                )
                passive_template = next(
                    r
                    for r in inventory
                    if r["type"] == row["Type"] and r["package"] == row["Package"]
                )
            if not info["footprint"]:
                if not passive_template:
                    raise ValueError("Select a footprint")
                footprint_text = (
                    lib.root
                    / "components/generic_models"
                    / passive_template["footprint"]
                ).read_text()
                info["footprint"] = cad.footprint_data(footprint_text)
                warnings.append(
                    "Using the selected generic package footprint with this imported model."
                )
            else:
                footprint_text = self.asset(draft["footprintAsset"], [".kicad_mod"])[
                    "path"
                ].read_text()
            shared_symbol = False
            if original is None and passive_template:
                original = cad.flatten_symbol(
                    (
                        lib.root
                        / "components/generic_models"
                        / passive_template["symbol"]
                    ).read_text(),
                    passive_template["symbolName"],
                )
                numbers = {
                    p["number"]
                    for p in info["footprint"]["pads"]
                    if p["number"] and p["type"] != "np_thru_hole"
                }
                if numbers != {"1", "2"}:
                    raise ValueError(
                        "The generic passive symbol requires pads 1 and 2; supply the correct symbol for this footprint"
                    )
                shared_symbol = True
            if draft.get("alternative"):
                if row["Type"] != "connector":
                    raise ValueError("Alternative layouts are for connectors")
                inference = info["inference"]
                if not inference["eligible"]:
                    raise ValueError(
                        "Alternative symbol unavailable: "
                        + "; ".join(inference["reasons"])
                    )
                if not draft.get("pinsConfirmed"):
                    raise ValueError(
                        "Check the inferred pin list before using a generic connector symbol"
                    )
                original = cad.connector_body_styles(
                    inference["count"],
                    draft.get("layout", "single"),
                    info["pins"],
                    working_name,
                )
            if original is None:
                raise ValueError(
                    "Select an original symbol or a reviewed connector layout"
                )
            for property_node in cad.children(original, "property"):
                if (
                    property_node[1].casefold()
                    in ("mpn", "manufacturer part number", "manufacturer_part_number")
                    and property_node[2].strip()
                    and property_node[2].strip().casefold() != row["MPN"].casefold()
                ):
                    warnings.append(
                        "The supplied symbol identifies MPN "
                        + str(property_node[2])
                        + ", which differs from the catalog MPN. Verify the selected files."
                    )
            # Generic replacement must not hide a mismatch; supplied symbols can be saved for review.
            pins = cad.symbol_pins(original)
            numbers = {p["number"] for p in pins}
            pads = {
                p["number"]
                for p in info["footprint"]["pads"]
                if p["number"] and p["type"] != "np_thru_hole"
            }
            if numbers != pads:
                unchanged_electrical_cad = bool(
                    same_edit
                    and mode == baseline["mode"]
                    and all(
                        draft.get(key, "") == baseline.get(key, "")
                        for key in ("symbolAsset", "symbolName", "footprintAsset")
                    )
                    and not draft.get("alternative")
                )
                if not unchanged_electrical_cad:
                    raise ValueError(
                        "Symbol and footprint pin numbers differ. "
                        + "Symbol: "
                        + ", ".join(sorted(numbers, key=cad.numeric_key))
                        + "; footprint: "
                        + ", ".join(sorted(pads, key=cad.numeric_key))
                        + ". Correct the selected files before saving."
                    )
                warnings.append(
                    "Existing symbol/footprint pin-number mismatch preserved. The electrical CAD is unchanged; verify the original part drawing before placement."
                )
            row["SymbolFile"] = folder + "/symbol.kicad_sym"
            row["FootprintFile"] = (
                folder + "/footprint.pretty/" + working_name + ".kicad_mod"
            )
            row["Symbol"] = nick + ":" + working_name
            row["Footprint"] = nick + ":" + working_name
            if same_edit and baseline["mode"] == "bespoke" and existing["AssetFolder"]:
                # Placed KiCad items identify a named symbol/footprint, not the
                # purchasing MPN. Keep those links and private filenames stable.
                for field in ("Symbol", "Footprint"):
                    file_field = field + "File"
                    if existing[field] and existing[file_field].startswith(
                        existing["AssetFolder"] + "/"
                    ):
                        row[field] = existing[field]
                        row[file_field] = (
                            folder
                            + existing[file_field][len(existing["AssetFolder"]) :]
                        )
            symbol_working_name = row["Symbol"].split(":", 1)[1]
            footprint_working_name = row["Footprint"].split(":", 1)[1]
            symbol_text = cad.symbol_library(
                original,
                symbol_working_name,
                dict(
                    Reference=row["Reference"],
                    Footprint=row["Footprint"],
                    Value=row["Value"],
                    Datasheet=row["Datasheet"],
                    PartID=row["ID"],
                    LibraryID=lib.id,
                ),
            )
            if shared_symbol:
                row["SymbolFile"] = (
                    "components/generic_models/" + passive_template["symbol"]
                )
                row["Symbol"] = (
                    lib.prefix
                    + "_"
                    + row["Type"]
                    + ":"
                    + passive_template["symbolName"]
                )
                symbol_text = inside(lib.root, row["SymbolFile"]).read_text()
            model_path = None
            model_action = draft.get(
                "modelAction", "preserve" if same_edit else "replace"
            )
            if model_action not in ("preserve", "replace", "remove"):
                raise ValueError("Choose a supported model action")
            preserve_models = bool(
                same_edit
                and model_action == "preserve"
                and draft.get("modelAsset", "") == baseline.get("modelAsset", "")
            )
            transform = draft.get("transform") or (
                info["footprint"]["models"][0] if info["footprint"]["models"] else None
            )
            if preserve_models:
                changed_transform = None
                model_index = None
                if (
                    draft.get("footprintAsset") == baseline.get("footprintAsset")
                    and baseline.get("modelIndex") is not None
                    and draft.get("transform")
                    and draft["transform"] != baseline.get("transform")
                ):
                    changed_transform = draft["transform"]
                    model_index = baseline["modelIndex"]
                moves = (
                    {existing["AssetFolder"]: folder}
                    if existing["AssetFolder"] and existing["AssetFolder"] != folder
                    else {}
                )
                footprint_text = cad.footprint_payload(
                    footprint_text,
                    footprint_working_name,
                    preserve_models=True,
                    transform=changed_transform,
                    transform_model_index=model_index,
                    path_moves=moves,
                )
            else:
                if draft.get("modelAsset") and model_action != "remove":
                    model = self.asset(draft["modelAsset"], [".step", ".stp"])
                    model_path = folder + "/model.step"
                    writes[model_path] = model["path"].read_bytes()
                    if len(info["footprint"]["models"]) > 1:
                        warnings.append(
                            "The selected STEP replaces multiple supplier model references. Check that it represents the complete component."
                        )
                elif info["footprint"]["models"]:
                    warnings.append(
                        "3D model references are removed because no local STEP file was selected."
                    )
                footprint_text = cad.footprint_payload(
                    footprint_text,
                    footprint_working_name,
                    "${MYCO_PARTS_DIR}/../" + model_path if model_path else None,
                    transform,
                )
            if not shared_symbol:
                writes[row["SymbolFile"]] = symbol_text.encode()
            writes[row["FootprintFile"]] = footprint_text.encode()
            info["proposedPins"] = pins
            info["footprint"] = cad.footprint_data(footprint_text)
        recipe_input, accessory_rows = resolve_inline_accessories(
            draft.get("recipe", {"version": 1, "items": []}), rows, row
        )
        recipe = validate_recipe(recipe_input, row["ID"], rows + accessory_rows)
        if row["Type"] != "connector" and recipe["items"]:
            warnings.append("Accessory list is attached to a non-connector component.")
        recipe_graph = {r["ID"]: lib.recipe(r) for r in rows if r["ID"] != row["ID"]}
        recipe_graph[row["ID"]] = recipe
        check_cycles(recipe_graph)
        if folder:
            writes[folder + "/component.json"] = json_bytes(
                dict(version=1, partID=row["ID"], libraryID=lib.id)
            )
        if (
            folder
            or recipe["items"]
            or (existing and inside(lib.root, lib.recipe_path(existing)).exists())
        ):
            writes[lib.recipe_path(row)] = json_bytes(recipe)
        if existing and lib.recipe_path(existing) != lib.recipe_path(row):
            deletes.append(lib.recipe_path(existing))
        if self.originals:
            writes[
                APPDATA
                + "/original-downloads/"
                + slug(row["ID"])
                + "-"
                + uuid.uuid4().hex[:12]
                + ".zip"
            ] = self.archive()
        updated = [r for r in rows if r["ID"] != row["ID"]] + accessory_rows + [row]
        writes[APPDATA + "/components.csv"] = csv_bytes(updated)
        derived_fingerprints = {}
        writes.update(lib.compiled(updated, writes, derived_fingerprints))
        token = uuid.uuid4().hex
        fingerprints = {
            name: digest(inside(lib.root, name).read_bytes())
            if inside(lib.root, name).is_file()
            else None
            for name in set(writes) | set(deletes)
        }
        fingerprints.update(derived_fingerprints)
        for field in ("SymbolFile", "FootprintFile"):
            if row[field] and row[field] not in writes:
                fingerprints[row[field]] = digest(
                    inside(lib.root, row[field]).read_bytes()
                )
        self.prepared = dict(
            token=token,
            revision=revision,
            libraryID=lib.id,
            writes=writes,
            deletes=deletes,
            row=row,
            existing=existing,
            fingerprints=fingerprints,
            draft=copy.deepcopy(draft),
            warnings=warnings,
            info=info,
            symbolText=symbol_text,
            footprintText=footprint_text,
        )
        # Preview files are temporary, never the authoritative library.
        if symbol_text:
            (self.root / "preview.kicad_sym").write_text(symbol_text)
        if footprint_text:
            pretty = self.root / "preview.pretty"
            pretty.mkdir(exist_ok=True)
            for path in pretty.glob("*.kicad_mod"):
                path.unlink()
            (
                pretty / (cad.footprint_data(footprint_text)["name"] + ".kicad_mod")
            ).write_text(footprint_text)
        changes = {
            c: dict(before=existing.get(c, ""), after=row[c])
            for c in COLUMNS
            if existing and existing.get(c, "") != row[c]
        }
        return dict(
            token=token,
            part=row,
            info=info,
            warnings=warnings,
            replacing=bool(existing),
            changes=changes,
            recipe=recipe,
            searchPath=f"{lib.name}/{category}/{row['MPN']}",
            revision=revision,
        )

    def commit(self, lib, token, replace=False):
        p = self.prepared
        if not p or p["token"] != token or p["libraryID"] != lib.id:
            raise ValueError("Review this import before saving")
        if p["existing"] and not replace:
            raise ValueError("Confirm replacement of the existing part")
        lib.transaction(p["writes"], p["revision"], p["deletes"], p["fingerprints"])
        self.prepared = None
        return p["row"]

    @staticmethod
    def _new_id(row, rows):
        candidate = slug(row["MPN"])
        ids = {r["ID"].casefold() for r in rows}
        if candidate.casefold() in ids:
            candidate = slug(row["Manufacturer"] + " " + row["MPN"])
        if candidate.casefold() in ids:
            candidate = candidate[:85] + "-" + uuid.uuid4().hex[:8]
        return candidate


def _normalize_changed_passive_specs(row, existing):
    """Validate edited numeric fields without forcing old CAD into bundled sizes.

    Unchanged legacy specifications may be incomplete. The normalizer's other
    inputs are validation scaffolding only; none are written to the catalog.
    """
    from .passives import normalize

    rating = "Power_W" if row["Type"] == "resistor" else "Voltage_VDC"
    fields = ("Value", "Tolerance", rating)
    changed = {field for field in fields if row[field] != existing[field]}
    if not changed:
        return
    probe = dict(
        Type=row["Type"],
        Description="",
        Package="0805",
        Tolerance="1%",
        Value="1" if row["Type"] == "resistor" else "1nF",
        **{rating: "1"},
    )
    probe.update({field: row[field] for field in changed})
    normalize(probe, probe)
    for field in changed:
        row[field] = probe[field]


def resolve_inline_accessories(recipe, rows, parent):
    """Stage typed accessory identities in the same save as their owning part."""
    added = []
    resolved = []
    for source in recipe.get("items", []):
        item = dict(source)
        if not item.get("partID"):
            manufacturer = str(item.get("manufacturer", "")).strip()
            mpn = str(item.get("mpn", "")).strip()
            if not manufacturer or not mpn:
                raise ValueError("Each accessory needs a manufacturer and part number")
            if (manufacturer.casefold(), mpn.casefold()) == (
                parent["Manufacturer"].casefold(),
                parent["MPN"].casefold(),
            ):
                raise ValueError("A component cannot be its own accessory")
            existing = next(
                (
                    r
                    for r in rows + added
                    if (r["Manufacturer"].casefold(), r["MPN"].casefold())
                    == (manufacturer.casefold(), mpn.casefold())
                ),
                None,
            )
            if existing is None:
                existing = {c: "" for c in COLUMNS}
                existing.update(
                    Manufacturer=manufacturer,
                    MPN=mpn,
                    Value=mpn,
                    Type="accessory",
                    Category="components/accessories",
                    CreatedUTC=timestamp(),
                    UpdatedUTC=timestamp(),
                )
                existing["ID"] = ImportSession._new_id(
                    existing, rows + added + [parent]
                )
                added.append(existing)
            item["partID"] = existing["ID"]
        resolved.append(item)
    return dict(version=1, items=resolved), added


def validate_recipe(recipe, parent, rows):
    ids = {r["ID"] for r in rows}
    items = []
    seen = set()
    for item in recipe.get("items", []):
        ident = item.get("partID")
        quantity = item.get("quantity")
        if ident not in ids:
            raise ValueError("Accessory is missing from the catalog: " + str(ident))
        if ident == parent or ident in seen:
            raise ValueError(
                "An accessory cannot reference itself or occur twice in one list"
            )
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ValueError("Accessory quantities must be positive whole numbers")
        items.append(
            dict(
                partID=ident, quantity=quantity, role=str(item.get("role", "accessory"))
            )
        )
        seen.add(ident)
    return dict(version=1, items=items)


def check_cycles(graph):
    def visit(node, ancestors):
        if node in ancestors:
            raise ValueError("Accessory recipes contain a cycle")
        for item in graph.get(node, {}).get("items", []):
            visit(item["partID"], ancestors | {node})

    for node in graph:
        visit(node, set())
