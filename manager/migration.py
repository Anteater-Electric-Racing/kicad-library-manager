"""Explicit, copy-only migration from the retired importer into a new library.

Never opens source SQLite databases or changes machine registrations. The CSV is
source authority; absent models remain reported absences, not guessed geometry.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import shutil
import tempfile
import zipfile

from . import cad
from .sexpr import Quoted as Q, children, parse, dump, value
from .storage import (
    APPDATA,
    COLUMNS,
    create_library,
    csv_bytes,
    digest,
    inside,
    install_portable_runtime,
    json_bytes,
    slug,
    timestamp,
)

LEGACY_APPDATA = "parts-library-appdata"


def inventory(source):
    """Hash every source file, rejecting symlinks instead of following them."""
    source = Path(source).expanduser().resolve()
    result = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Source symlink is unsupported: {path}")
        if path.is_file():
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            result[path.relative_to(source).as_posix()] = {
                "sha256": h.hexdigest(),
                "bytes": path.stat().st_size,
            }
    return result


class LegacySource:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.appdata = self.root / LEGACY_APPDATA
        self.catalog = self.appdata / "components.csv"
        if not self.catalog.is_file():
            raise ValueError("Source must contain parts-library-appdata/components.csv")
        with self.catalog.open(encoding="utf-8-sig", newline="") as stream:
            self.rows = list(csv.DictReader(stream))
        ids = [r.get("ID", "") for r in self.rows]
        if not all(ids) or len(set(ids)) != len(ids):
            raise ValueError("Legacy catalog has missing or duplicate IDs")
        self.symbols = self._table("sym-lib-table")
        self.footprints = self._table("fp-lib-table")

    def _table(self, filename):
        path = self.appdata / filename
        result = {}
        if path.is_file():
            for entry in children(parse(path.read_text()), "lib"):
                if str(value(entry, "type")) == "KiCad":
                    result[str(value(entry, "name"))] = str(value(entry, "uri"))
        return result

    def resolve(self, text, relative_to=None):
        """Use explicit local paths; repair only the known old appdata prefix."""
        text = str(text).replace("\\", "/")
        candidates = []
        if text.startswith("${MYCO_PARTS_DIR}/"):
            tail = text[len("${MYCO_PARTS_DIR}/") :]
            candidates.append(self.appdata / tail)
            if not tail.startswith("../"):
                candidates.append(self.root / tail)
        elif "${" not in text:
            path = Path(text)
            candidates.append(
                path if path.is_absolute() else (relative_to or self.root) / path
            )
        for path in candidates:
            resolved = path.resolve()
            if resolved.is_relative_to(self.root) and resolved.exists():
                if path.is_symlink():
                    raise ValueError(f"Source asset is a symlink: {path}")
                return resolved
        return None

    def symbol(self, qualified):
        nickname, separator, name = qualified.partition(":")
        if not separator:
            raise ValueError(f"Invalid legacy symbol link: {qualified}")
        path = self.resolve(self.symbols.get(nickname, ""))
        if not path or not path.is_file():
            candidates = list((self.root / "symbol").rglob(nickname + ".kicad_sym"))
            if len(candidates) != 1:
                raise ValueError(f"Cannot uniquely locate symbol library: {qualified}")
            path = candidates[0]
        # Resolving inheritance now catches missing parents without inventing pins.
        cad.flatten_symbol(path.read_text(), name)
        return path, name

    def footprint(self, qualified):
        nickname, separator, name = qualified.partition(":")
        if not separator:
            raise ValueError(f"Invalid legacy footprint link: {qualified}")
        library = self.resolve(self.footprints.get(nickname, ""))
        path = library / (name + ".kicad_mod") if library else None
        if path is None or not path.is_file():
            path = (
                self.root
                / "footprints"
                / (nickname + ".pretty")
                / (name + ".kicad_mod")
            )
        if not path.is_file() or not path.resolve().is_relative_to(self.root):
            raise ValueError(f"Missing legacy footprint: {qualified}")
        return path, name


def audit_legacy(source):
    old = LegacySource(source)
    files = inventory(old.root)
    groups = {}
    errors = []
    for row in old.rows:
        key = row.get("Category") or row.get("Type") or "other"
        groups[key] = groups.get(key, 0) + 1
        for field, resolver in [("Symbol", old.symbol), ("Footprint", old.footprint)]:
            if row.get(field):
                try:
                    resolver(row[field])
                except ValueError as exc:
                    errors.append({"partID": row["ID"], "error": str(exc)})
    return dict(
        source=str(old.root),
        rowCount=len(old.rows),
        categories=groups,
        fileCount=len(files),
        bytes=sum(x["bytes"] for x in files.values()),
        errors=errors,
        files=files,
    )


def _type(row):
    kind = row.get("Category", "").lower()
    if kind in ("resistor", "capacitor", "connector", "ic", "accessory"):
        return "IC" if kind == "ic" else kind
    return {"R": "resistor", "C": "capacitor", "J": "connector", "U": "IC"}.get(
        row.get("Type") or row.get("Reference"), "other"
    )


def _category(row, kind):
    if kind in ("resistor", "capacitor"):
        return "components/" + kind + "s"
    if kind == "connector":
        folder = row.get("Folder", "").replace("\\", "/")
        tail = folder.partition("symbol/connector/")[2]
        if tail and tail not in ("generic", row["ID"], row.get("MPN")):
            return "components/connectors/" + "/".join(
                slug(x) for x in Path(tail).parts
            )
        return "components/connectors"
    return "components/" + (
        "ICs" if kind == "IC" else "accessories" if kind == "accessory" else "other"
    )


def _metadata(oldrow):
    row = {key: oldrow.get(key, "") for key in COLUMNS}
    row.update(Status="", CreatedUTC=timestamp(), UpdatedUTC=timestamp())
    reserved = {"RecordKind", "Folder", "LocalDatasheet", "Status", "Type", "Category"}
    extras = {
        key: val
        for key, val in oldrow.items()
        if key not in COLUMNS and key not in reserved and val
    }
    if extras:
        details = "Legacy metadata (historical values): " + "; ".join(
            f"{key}: {val}" for key, val in extras.items()
        )
        row["Notes"] = "\n".join(x for x in (row.get("Notes", ""), details) if x)
    return row


def _copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        raise ValueError(f"Migration destination collision: {destination}")
    shutil.copy2(source, destination)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError(f"Migration asset collision: {path}")
    path.write_bytes(payload)


def _footprint(old, source, root, destination, model_folder, warnings, part_id):
    before = parse(source.read_text())
    node = parse(source.read_text())
    node[1] = Q(destination.stem)
    resolved_models = []
    for model in children(node, "model"):
        original = str(model[1])
        local = old.resolve(original, source.parent)
        if local and local.is_file():
            target = model_folder / slug(local.name)
            if target.exists() and target.read_bytes() != local.read_bytes():
                target = target.with_name(
                    target.stem + "-" + digest(local.read_bytes())[:8] + target.suffix
                )
            _copy(local, target)
            model[1] = Q("${MYCO_PARTS_DIR}/../" + target.relative_to(root).as_posix())
            resolved_models.append(
                {
                    "source": local.relative_to(old.root).as_posix(),
                    "destination": target.relative_to(root).as_posix(),
                    "sha256": digest(local.read_bytes()),
                }
            )
        else:
            warnings.append(
                {
                    "partID": part_id,
                    "kind": "missing-model",
                    "path": original,
                    "message": "Unresolved source model reference retained; no substitute or alignment inferred.",
                }
            )
    payload = (dump(node) + "\n").encode()
    _write(destination, payload)
    if children(before, "pad") != children(node, "pad"):
        raise AssertionError("Migration changed footprint pads")
    if [x[2:] for x in children(before, "model")] != [
        x[2:] for x in children(node, "model")
    ]:
        raise AssertionError("Migration changed model transformations")
    return resolved_models


def _migrate_row(old, lib, original, warnings):
    row = _metadata(original)
    row["Type"] = kind = _type(original)
    row["Category"] = _category(original, kind)
    row["AssetFolder"] = ""
    record = {"partID": row["ID"], "sourceRow": original, "models": []}
    if (
        kind == "accessory"
        and not original.get("Symbol")
        and not original.get("Footprint")
    ):
        row.update(Symbol="", SymbolFile="", Footprint="", FootprintFile="")
        return row, record
    shared = kind in ("resistor", "capacitor")
    folder = (
        f"components/generic_models/legacy/{kind}s"
        if shared
        else row["Category"] + "/" + slug(row["MPN"] or row["ID"])
    )
    if not shared:
        # Manufacturer aliases or duplicate sanitized MPNs get stable suffixes.
        marker = lib.root / folder / "component.json"
        if marker.exists():
            folder += "-" + digest(row["ID"].encode())[:8]
        row["AssetFolder"] = folder
        _write(
            lib.root / folder / "component.json",
            json_bytes(dict(version=1, partID=row["ID"], libraryID=lib.id)),
        )
        _write(
            lib.root / folder / "recipes.json", json_bytes(dict(version=1, items=[]))
        )
    sym_path, sym_name = (
        old.symbol(original["Symbol"]) if original.get("Symbol") else (None, None)
    )
    fp_path, fp_name = (
        old.footprint(original["Footprint"])
        if original.get("Footprint")
        else (None, None)
    )
    nick = lib.prefix + "_" + digest(row["ID"].encode())[:12]
    if fp_path:
        fp_nick = (
            lib.prefix
            + "_legacy_"
            + digest(str(fp_path.parent.relative_to(old.root)).encode())[:12]
            if shared
            else nick
        )
        row["FootprintFile"] = (
            folder
            + "/"
            + (slug(fp_path.parent.stem) if shared else "footprint")
            + ".pretty/"
            + slug(fp_name)
            + ".kicad_mod"
        )
        row["Footprint"] = fp_nick + ":" + slug(fp_name)
        record["models"] = _footprint(
            old,
            fp_path,
            lib.root,
            inside(lib.root, row["FootprintFile"]),
            lib.root / folder / "models-3d",
            warnings,
            row["ID"],
        )
        record["footprintSource"] = fp_path.relative_to(old.root).as_posix()
        if not children(parse(fp_path.read_text()), "model"):
            candidates = [
                p
                for p in (old.root / "STEP").glob("*")
                if p.stem.casefold() in {row["ID"].casefold(), row["MPN"].casefold()}
                and p.suffix.lower() in (".step", ".stp")
            ]
            for model in candidates:
                _copy(model, lib.root / folder / "models-3d" / slug(model.name))
                warnings.append(
                    {
                        "partID": row["ID"],
                        "kind": "unattached-model",
                        "path": model.relative_to(old.root).as_posix(),
                        "message": "Copied existing model beside component; source footprint had no attachment, so no position was guessed.",
                    }
                )
    else:
        row.update(Footprint="", FootprintFile="")
        warnings.append(
            {
                "partID": row["ID"],
                "kind": "missing-footprint",
                "message": "Catalog had no footprint.",
            }
        )
    if sym_path:
        sym_nick = (
            lib.prefix
            + "_legacy_"
            + digest(str(sym_path.relative_to(old.root)).encode())[:12]
            if shared
            else nick
        )
        row["SymbolFile"] = (
            folder + "/" + (slug(sym_path.stem) if shared else "symbol") + ".kicad_sym"
        )
        row["Symbol"] = sym_nick + ":" + sym_name
        if shared:
            # Shared source symbols preserve exact native definitions; database fields supply IDs.
            _copy(sym_path, lib.root / row["SymbolFile"])
        else:
            node = cad.flatten_symbol(sym_path.read_text(), sym_name)
            before = cad.symbol_pins(node)
            payload = cad.symbol_library(
                node,
                sym_name,
                dict(
                    Reference=row["Reference"],
                    Footprint=row["Footprint"],
                    Value=row["Value"],
                    Datasheet=row["Datasheet"],
                    PartID=row["ID"],
                    LibraryID=lib.id,
                ),
            )
            if cad.symbol_pins(cad.flatten_symbol(payload, sym_name)) != before:
                raise AssertionError("Migration changed symbol pins")
            _write(lib.root / row["SymbolFile"], payload.encode())
        record["symbolSource"] = sym_path.relative_to(old.root).as_posix()
    else:
        row.update(Symbol="", SymbolFile="")
        warnings.append(
            {
                "partID": row["ID"],
                "kind": "missing-symbol",
                "message": "Catalog had no symbol; none generated.",
            }
        )
    if not shared:
        local_document = old.resolve(original.get("LocalDatasheet", ""))
        if local_document and local_document.is_file():
            _copy(local_document, lib.root / folder / "documents" / local_document.name)
        supporting = old.root / "symbol/supporting-data" / row["ID"]
        if supporting.is_dir():
            shutil.copytree(
                supporting,
                lib.root / folder / "documents/supporting-data",
                dirs_exist_ok=True,
            )
    record["destinationRow"] = row
    return row, record


def migrate_legacy(source, destination, *, install_runtime=False):
    """Build a separate sibling, prove source unchanged, then publish by rename."""
    old = LegacySource(source)
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError(
            "Migration destination must not already exist; no overwrite is supported"
        )
    if destination.is_relative_to(old.root) or old.root.is_relative_to(destination):
        raise ValueError("Migration source and destination must be separate folders")
    before = inventory(old.root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".library-migration-", dir=destination.parent
    ) as staging:
        stage_root = Path(staging) / destination.name
        lib = create_library(stage_root, install_runtime=False)
        if lib.manifest.get("formatVersion") != 2 or APPDATA != "appdata":
            raise ValueError(
                "Migration requires Library Manager folder format version 2"
            )
        warnings, rows, records = [], [], []
        for original in old.rows:
            row, record = _migrate_row(old, lib, original, warnings)
            rows.append(row)
            records.append(record)
        originals = old.root / "Component downloads"
        if originals.is_dir():
            shutil.copytree(
                originals, lib.appdata / "original-downloads/legacy", dirs_exist_ok=True
            )
        logos = []
        for path in sorted(old.root.rglob("*.kicad_mod")):
            rel = path.relative_to(old.root)
            if "logo" in path.name.casefold() or (
                "footprints" in rel.parts
                and any("logo" in p.casefold() for p in rel.parts)
            ):
                if "backups" in rel.parts or "Component downloads" in rel.parts:
                    continue
                target = (
                    lib.root / "components/logos" / rel
                    if any(part.endswith(".pretty") for part in rel.parts)
                    else lib.root / "components/logos/LegacyLogos.pretty" / path.name
                )
                _copy(path, target)
                logos.append(
                    {
                        "source": rel.as_posix(),
                        "destination": target.relative_to(lib.root).as_posix(),
                    }
                )
        migration = lib.appdata / "migration"
        migration.mkdir()
        _copy(old.catalog, migration / "source-catalog.csv")
        (migration / "source-inventory.json").write_bytes(json_bytes(before))
        with zipfile.ZipFile(
            migration / "legacy-source-snapshot.zip", "w", zipfile.ZIP_DEFLATED
        ) as archive:
            for name in before:
                archive.write(old.root / name, name)
        (lib.appdata / "components.csv").write_bytes(csv_bytes(rows))
        for name, data in lib.compiled(rows).items():
            target = inside(lib.root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        after = inventory(old.root)
        if before != after:
            raise ValueError(
                "Source changed during migration; destination was not published. Retry while the old library is idle."
            )
        report = dict(
            version=1,
            createdUTC=timestamp(),
            source=str(old.root),
            destination=str(destination),
            libraryID=lib.id,
            sourceUnchanged=True,
            sourceFileCount=len(before),
            rowCount=len(rows),
            preservedIDs=[r["ID"] for r in rows],
            warnings=warnings,
            rows=records,
            logos=logos,
            originals="appdata/original-downloads/legacy",
            snapshot="appdata/migration/legacy-source-snapshot.zip",
            registrationsChanged=False,
            recipesInferred=False,
        )
        (migration / "report.json").write_bytes(json_bytes(report))
        (migration / "README.md").write_text(_report_markdown(report))
        if install_runtime:
            install_portable_runtime(lib.root)
        # Refuse a destination created by somebody else while conversion ran.
        if destination.exists():
            raise ValueError(
                "Migration destination appeared during conversion; no overwrite performed"
            )
        stage_root.rename(destination)
    return report


def _report_markdown(report):
    lines = [
        "# Legacy library conversion",
        "",
        f"Converted {report['rowCount']} active catalog rows with their IDs preserved.",
        f"Verified all {report['sourceFileCount']} source files unchanged by SHA-256.",
        "",
        "The source library and KiCad registrations were left unchanged. No accessory pairing, pin mapping, or model alignment was inferred.",
        "",
        "The exact original catalog, complete source ZIP, and file hash inventory are here. Original downloads are under `appdata/original-downloads/legacy`; passive PDFs remain archive material only. Old metadata unsupported by the new catalog is retained in each report row and in Notes where meaningful.",
        "",
        "Existing KiCad designs retain their previous library references. Connect this library explicitly before placing new components; existing designs require deliberate relinking.",
        "",
        "## Items carried forward",
        "",
    ]
    for item in report["warnings"]:
        lines.append(
            f"- **{item['partID']}**: {item['message']} {item.get('path', '')}"
        )
    if not report["warnings"]:
        lines.append("No missing asset warnings.")
    return "\n".join(lines) + "\n"
