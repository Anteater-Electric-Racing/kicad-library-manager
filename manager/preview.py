"""Read-only catalog CAD previews rendered outside the selected library."""

from pathlib import Path
import tempfile

from . import cad, kicad
from .storage import inside


def component_preview(lib, ident, kind):
    row = next((row for row in lib.rows() if row["ID"] == ident), None)
    if row is None:
        raise ValueError("Component no longer exists")
    if kind == "symbol":
        if not row["SymbolFile"]:
            return {"svgs": []}
        return {"svgs": kicad.render(
            "sym", inside(lib.root, row["SymbolFile"]), row["Symbol"].split(":", 1)[-1]
        )}
    if kind not in ("footprint", "model", "step"):
        raise ValueError("Unknown component preview")
    if not row["FootprintFile"]:
        if kind == "step":
            raise ValueError("No local STEP model available")
        return {"svgs": []} if kind == "footprint" else {"footprint": None, "model": None}
    source = inside(lib.root, row["FootprintFile"])
    text = source.read_text()
    footprint = cad.footprint_data(text)
    if kind == "footprint":
        with tempfile.TemporaryDirectory(prefix="manager-preview-") as directory:
            pretty = Path(directory) / "preview.pretty"
            pretty.mkdir()
            (pretty / source.name).write_text(text)
            return {"svgs": kicad.render("fp", pretty)}
    for model in footprint["models"]:
        prefix = "${MYCO_PARTS_DIR}/../"
        if not model["path"].startswith(prefix):
            continue
        path = inside(lib.root, model["path"].removeprefix(prefix))
        if path.suffix.lower() in (".step", ".stp") and path.is_file():
            if kind == "step":
                return path.read_bytes()
            return {"footprint": footprint, "model": model}
    if kind == "step":
        raise ValueError("No local STEP model available")
    return {"footprint": footprint, "model": None}
