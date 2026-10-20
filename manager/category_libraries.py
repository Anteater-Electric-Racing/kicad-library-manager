"""Derived folder-category footprint libraries; working CAD stays authoritative."""

import json
import re
from pathlib import PurePosixPath

from .sexpr import Quoted as Q, parse, dump, children
from .storage import APPDATA, digest, inside, json_bytes, slug

INDEX = APPDATA + "/category-libraries.json"
BASE = APPDATA + "/generated/categories"


def category_label(category):
    parts = list(PurePosixPath(category).parts)
    if parts and parts[0].casefold() == "components":
        parts.pop(0)
    if not parts:
        return "Virtus - Components"
    words = [re.sub(r"[_-]+", " ", p).strip() for p in parts]
    words = ["IC" if p.casefold() in {"ic", "ics"} else " ".join(w[:1].upper() + w[1:] for w in p.split()) for p in words]
    if parts[0].casefold() in {"connector", "connectors"}:
        words = words[1:] or ["Connectors"]
        if "connector" not in words[-1].casefold():
            words[-1] += " Connectors"
    return "Virtus - " + " - ".join(words)


def footprints(lib, rows, pending, fingerprints):
    """Return writes, visible/hidden registrations and database footprint links.

    The index reserves names and remembers previous category aliases. It contains
    no editable product data. Old aliases continue following the same source CAD.
    """
    path = lib.appdata / "category-libraries.json"
    raw_index = path.read_bytes() if path.exists() else None
    fingerprints[INDEX] = digest(raw_index) if raw_index is not None else None
    index = json.loads(raw_index) if raw_index is not None else {"version": 1, "categories": {}}
    if index.get("version") != 1:
        raise ValueError("Unsupported category-library index")
    categories = index["categories"]
    rows = list(rows)
    for pretty in sorted((lib.root / "components/logos").rglob("*.pretty")):
        if not pretty.is_dir() or pretty.is_symlink():
            continue
        rel = pretty.relative_to(lib.root).as_posix()
        nickname = lib.prefix + "_logos_" + digest(rel.encode())[:10]
        for file in sorted(pretty.glob("*.kicad_mod")):
            rows.append(dict(ID="logo:" + rel + "/" + file.name,
                             Category=pretty.parent.relative_to(lib.root).as_posix(),
                             Symbol="", Footprint=nickname + ":" + file.stem,
                             FootprintFile=file.relative_to(lib.root).as_posix()))
    labels = {item["name"].casefold() for item in categories.values()}
    for category in sorted({r["Category"] for r in rows if r["Symbol"] or r["Footprint"]}):
        if category not in categories:
            name = category_label(category)
            if name.casefold() in labels:
                name += " (" + digest(category.encode())[:10] + ")"
            labels.add(name.casefold())
            categories[category] = {"name": name, "items": {}}
    sources = {r["Footprint"]: r for r in rows if r["Footprint"]}
    links = {}
    active = set()
    for row in sorted(rows, key=lambda r: (r["Category"], r["ID"])):
        source = row["Footprint"]
        if not source:
            continue
        category = row["Category"]
        group = categories[category]
        active.add(category)
        if source not in group["items"]:
            # Keep the existing item name, disambiguating unrelated CAD with the
            # same name. Previously allocated names never change on later saves.
            name = slug(source.split(":", 1)[1])
            used = {n.casefold() for n in group["items"].values()}
            if name.casefold() in used:
                name = name[:80] + " (" + digest(source.encode())[:12] + ")"
            if name.casefold() in used:
                raise ValueError("Conflicting generated footprint names")
            group["items"][source] = name
        links[row["ID"]] = group["name"] + ":" + group["items"][source]
    writes, entries = {}, {}
    for category, group in sorted(categories.items()):
        folder = BASE + "/" + digest(category.encode())[:24] + ".pretty"
        count = 0
        for source, name in group["items"].items():
            if source not in sources:
                continue
            row = sources[source]
            file = row["FootprintFile"]
            raw = pending[file] if file in pending else inside(lib.root, file).read_bytes()
            if file not in pending:
                fingerprints[file] = digest(raw)
            node = parse(raw.decode("utf-8-sig"))
            if node[0] not in {"footprint", "module"}:
                raise ValueError("Expected a working KiCad footprint: " + file)
            node[1] = Q(name)
            # Relative paths originally resolve from the working .pretty folder.
            # Preserve that location when emitting a projection elsewhere.
            for model in children(node, "model"):
                ref = str(model[1])
                if ref and "$" not in ref and not PurePosixPath(ref).is_absolute() and not re.match(r"^[A-Za-z]:", ref):
                    model[1] = Q("${MYCO_PARTS_DIR}/../" + str(PurePosixPath(file).parent / ref))
            writes[folder + "/" + name + ".kicad_mod"] = (dump(node) + "\n").encode()
            count += 1
        if count:
            entries[group["name"]] = ("${MYCO_PARTS_DIR}/generated/categories/" + PurePosixPath(folder).name, category not in active)
    writes[INDEX] = json_bytes(index)
    return writes, entries, links, {c: g["name"] for c, g in categories.items()}
