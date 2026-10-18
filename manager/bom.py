"""KiCad external BOM generator with auditable fixed accessory expansion."""

import csv
import io
from pathlib import Path
import xml.etree.ElementTree as ET
from .importer import check_cycles
from .storage import digest, json_bytes, timestamp


def truth(value):
    return str(value).strip().casefold() in (
        "1",
        "true",
        "yes",
        "dnp",
        "exclude_from_bom",
    )


def read_design(path):
    data = Path(path).read_bytes()
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("BOM XML exceeds 64 MiB")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML entities are not supported")
    tree = ET.fromstring(data)
    instances = []
    for comp in tree.findall("./components/comp"):
        fields = {
            f.get("name", ""): f.text or "" for f in comp.findall("./fields/field")
        }
        for p in comp.findall("./property"):
            fields[p.get("name", "")] = p.get("value", "true")
        if truth(fields.get("dnp", fields.get("DNP", ""))) or truth(
            fields.get("exclude_from_bom", fields.get("Exclude from BOM", ""))
        ):
            continue
        instances.append(
            dict(
                ref=comp.get("ref", ""),
                partID=fields.get("PartID", ""),
                libraryID=fields.get("LibraryID", ""),
                value=comp.findtext("value", ""),
                mpn=fields.get("MPN", ""),
                manufacturer=fields.get("Manufacturer", ""),
                accessoryOf=fields.get("AccessoryOf", ""),
                fields=fields,
            )
        )
    return instances, data


def expand(lib, instances):
    rows = {r["ID"]: r for r in lib.rows()}
    recipes = {ident: lib.recipe(row) for ident, row in rows.items()}
    check_cycles(recipes)
    lines = []
    warnings = []
    seen_refs = set()
    owned = {}
    for instance in instances:
        if instance["ref"] in seen_refs:
            raise ValueError(
                "Duplicate component reference in BOM input: " + instance["ref"]
            )
        seen_refs.add(instance["ref"])
        if instance.get("accessoryOf"):
            if not instance.get("partID") or instance.get("libraryID") != lib.id:
                raise ValueError(
                    "AccessoryOf requires a managed part from this library"
                )
            owned.setdefault((instance["accessoryOf"], instance["partID"]), []).append(
                instance
            )
    used_owned = set()

    def append(ident, qty, parent, kind, trail):
        if ident not in rows:
            raise ValueError("Missing accessory/catalog record: " + ident)
        row = rows[ident]
        lines.append(
            dict(
                PartID=ident,
                Manufacturer=row["Manufacturer"],
                MPN=row["MPN"],
                Description=row["Description"],
                Quantity=qty,
                Kind=kind,
                Reference=parent,
                Reason=" → ".join(trail),
                Datasheet=row["Datasheet"],
            )
        )
        for item in recipes[ident]["items"]:
            child_qty = qty * item["quantity"]
            explicit = owned.get((parent, item["partID"]), [])
            if explicit:
                if len(trail) > 2:
                    raise ValueError(
                        "AccessoryOf cannot implicitly resolve a nested accessory recipe"
                    )
                if len(explicit) != child_qty:
                    raise ValueError(
                        f"{parent}: explicit accessory count does not match recipe quantity for {item['partID']}"
                    )
                used_owned.update(i["ref"] for i in explicit)
            append(
                item["partID"], child_qty, parent, "accessory", trail + [item["partID"]]
            )

    for instance in instances:
        if instance.get("accessoryOf"):
            continue
        ident = instance.get("partID")
        if ident and instance.get("libraryID") == lib.id:
            append(ident, 1, instance["ref"], "PCB", [instance["ref"], ident])
        elif ident:
            raise ValueError(
                instance["ref"]
                + ": part belongs to another library; export with the correct library"
            )
        else:
            lines.append(
                dict(
                    PartID="",
                    Manufacturer=instance.get("manufacturer", ""),
                    MPN=instance.get("mpn") or instance["value"],
                    Description=instance["value"],
                    Quantity=1,
                    Kind="PCB",
                    Reference=instance["ref"],
                    Reason=instance["ref"],
                    Datasheet="",
                )
            )
            warnings.append(
                instance["ref"] + ": unmanaged component; no accessory expansion"
            )
    unclaimed = {i["ref"] for i in instances if i.get("accessoryOf")} - used_owned
    if unclaimed:
        raise ValueError(
            "AccessoryOf references were not claimed by a parent recipe: "
            + ", ".join(sorted(unclaimed))
        )
    grouped = {}
    for line in lines:
        key = (line["PartID"], line["Manufacturer"], line["MPN"])
        if key not in grouped:
            grouped[key] = dict(
                line, Quantity=0, Reference=set(), Reason=set(), Kind=set()
            )
        g = grouped[key]
        g["Quantity"] += line["Quantity"]
        g["Reference"].add(line["Reference"])
        g["Reason"].add(line["Reason"])
        g["Kind"].add(line["Kind"])
    for g in grouped.values():
        for field in ("Reference", "Reason", "Kind"):
            g[field] = "; ".join(sorted(g[field]))
    return dict(
        lines=lines,
        purchasing=list(grouped.values()),
        warnings=sorted(set(warnings)),
        recipes=recipes,
    )


def export(lib, input_file, output_file):
    instances, data = read_design(input_file)
    result = expand(lib, instances)
    output = Path(output_file).expanduser().resolve()
    if output == Path(input_file).resolve():
        raise ValueError("BOM output cannot overwrite its input")
    if not output.suffix:
        output = output.with_suffix(".csv")
    columns = [
        "PartID",
        "Manufacturer",
        "MPN",
        "Description",
        "Quantity",
        "Kind",
        "Reference",
        "Reason",
        "Datasheet",
    ]

    def csv_text(rows):
        f = io.StringIO(newline="")
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        # Excel opens exported CSV; prevent manufacturer text being evaluated as formulas.
        w.writerows(
            {
                k: (
                    "'" + v
                    if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                    else v
                )
                for k, v in row.items()
            }
            for row in rows
        )
        return f.getvalue()

    output.parent.mkdir(parents=True, exist_ok=True)
    outputs = {
        output: csv_text(result["purchasing"]),
        output.with_name(output.stem + "-detail.csv"): csv_text(result["lines"]),
        output.with_name(output.stem + "-pcb.csv"): csv_text(
            [r for r in result["lines"] if r["Kind"] == "PCB"]
        ),
        output.with_name(output.stem + "-accessories.csv"): csv_text(
            [r for r in result["lines"] if r["Kind"] == "accessory"]
        ),
    }
    snapshot = dict(
        version=1,
        created=timestamp(),
        libraryID=lib.id,
        libraryRevision=lib.revision(),
        inputSHA256=digest(data),
        instances=instances,
        catalog=lib.rows(),
        **result,
    )
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8-sig")
    snapshot_path = output.with_name(output.stem + "-snapshot.json")
    snapshot_path.write_bytes(json_bytes(snapshot))
    return dict(
        files=[str(p) for p in outputs] + [str(snapshot_path)],
        warnings=result["warnings"],
    )
