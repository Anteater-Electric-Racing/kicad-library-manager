"""Bundle a small, explicit package collection from a supplied KiCad installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

PACKAGES = [
    ("TO-220-3_Horizontal_TabDown", "TO-220 · 3 pins · horizontal, tab down", "Package_TO_SOT_THT"),
    ("SOT-23", "SOT-23 · 3 pins", "Package_TO_SOT_SMD"),
    ("SOT-23-5", "SOT-23 · 5 pins", "Package_TO_SOT_SMD"),
    ("SOT-23-6", "SOT-23 · 6 pins", "Package_TO_SOT_SMD"),
    ("SOIC-8_3.9x4.9mm_P1.27mm", "SOIC-8 · 3.9 × 4.9 mm · 1.27 mm pitch", "Package_SO"),
    ("TSSOP-8_3x3mm_P0.65mm", "TSSOP-8 · 3 × 3 mm · 0.65 mm pitch", "Package_SO"),
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kicad_share", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "resources/generic_models"
    out = root / "standard_packages"
    inventory = []
    for name, label, family in PACKAGES:
        entry = dict(id=name, label=label, source=family + ":" + name)
        for key, source, dest in (
            ("footprint", f"footprints/{family}.pretty/{name}.kicad_mod", f"StandardPackages.pretty/{name}.kicad_mod"),
            ("model", f"3dmodels/{family}.3dshapes/{name}.step", f"models-3d/{name}.step"),
        ):
            target = out / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.kicad_share / source, target)
            entry[key] = dest
            entry[key + "SHA256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        inventory.append(entry)
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    shutil.copy2(root / "LICENSE-KICAD.md", out / "LICENSE-KICAD.md")
    (out / "ATTRIBUTION.md").write_text("""# Standard package CAD

Footprints and STEP models copied unchanged from the installed KiCad 10.0.1 distribution, https://gitlab.com/kicad/libraries . Copyright KiCad library contributors; CC BY-SA 4.0 with the KiCad libraries exception (LICENSE-KICAD.md). inventory.json records original library names and SHA-256 hashes.

TO-220 is the three-lead Horizontal_TabDown variant. All pin numbering, pad geometry and model transforms are upstream originals. Package selection does not establish a device's electrical pin mapping. The importer rewrites the working model URI to the saved component's local STEP file.
""")
    print(f"Bundled {len(inventory)} standard packages in {out}")
