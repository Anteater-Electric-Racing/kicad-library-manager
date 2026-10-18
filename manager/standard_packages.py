"""Bundled package templates; choosing one only stages session-local CAD."""
import json
from .storage import SOURCE_ROOT, digest, inside

ROOT = SOURCE_ROOT / "resources/generic_models/standard_packages"


def inventory():
    return json.loads((ROOT / "inventory.json").read_text())


def select(session, package):
    entry = next((item for item in inventory() if item["id"] == package), None)
    if entry is None:
        raise ValueError("Select a bundled standard package")
    result = {}
    for key in ("footprint", "model"):
        name = "standard_packages/" + entry[key]
        payload = inside(ROOT, entry[key]).read_bytes()
        if digest(payload) != entry[key + "SHA256"]:
            raise ValueError("Bundled standard package changed: " + package)
        session.upload(name, payload)
        ident = digest(name.encode())[:24]
        session.assets[ident]["standardPackage"] = package
        result[key + "Asset"] = ident
    for filename in ("ATTRIBUTION.md", "LICENSE-KICAD.md", "inventory.json"):
        session.upload("standard_packages/" + filename, (ROOT / filename).read_bytes())
    return dict(inventory=session.inventory(), package=package, **result)


def template_writes(session, lib, footprint_asset):
    """Copy selected reference templates with the component's existing transaction."""
    package = session.assets.get(footprint_asset, {}).get("standardPackage")
    if not package:
        return {}
    entry = next(item for item in inventory() if item["id"] == package)
    writes = {}
    for name in (entry["footprint"], entry["model"], "ATTRIBUTION.md", "LICENSE-KICAD.md"):
        target = "components/generic_models/standard_packages/" + name
        payload = inside(ROOT, name).read_bytes()
        existing = inside(lib.root, target)
        if existing.exists():
            if existing.read_bytes() != payload:
                raise ValueError("Standard package template already exists with different content: " + target)
        else:
            writes[target] = payload
    return writes
