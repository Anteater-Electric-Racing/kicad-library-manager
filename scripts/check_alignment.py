"""Compare our 3D transform convention with actual KiCad STEP export geometry.

Creates only synthetic boards and exports in a disposable directory.
"""

from pathlib import Path
import json
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager.cad import footprint_payload
from manager.sexpr import parse, dump, children, Quoted as Q
from manager.kicad import cli_path

root = Path(__file__).resolve().parents[1]
model = root / "resources/generic_models/models-3d/R_0805_2012Metric.step"
footprint = (
    root
    / "resources/generic_models/footprints/Resistor.pretty/R_0805_2012Metric.kicad_mod"
).read_text()
transforms = [
    dict(offset=[0, 0, 0], rotate=[0, 0, 0], scale=[1, 1, 1]),
    dict(offset=[3, 4, 1.5], rotate=[20, 35, 90], scale=[1, 1, 1]),
]
with tempfile.TemporaryDirectory(prefix="library-alignment-check-") as directory:
    directory = Path(directory)
    for i, transform in enumerate(transforms):
        fp = parse(footprint_payload(footprint, "Fixture", str(model), transform))
        fp = [
            v
            for v in fp
            if not (
                isinstance(v, list)
                and v
                and v[0] in ("version", "generator", "generator_version")
            )
        ]
        fp.append(["at", "0", "0"])
        for prop in children(fp, "property"):
            if prop[1] == "Reference":
                prop[2] = Q("R1")
        board = parse("""(kicad_pcb (version 20240108) (generator pcbnew)
          (general (thickness 1.6)) (paper "A4")
          (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (37 "F.SilkS" user) (44 "Edge.Cuts" user) (49 "F.Fab" user))
          (setup (pad_to_mask_clearance 0))
          (gr_rect (start -10 -10) (end 10 10) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts")))""")
        board.append(fp)
        source = directory / f"fixture-{i}.kicad_pcb"
        source.write_text(dump(board))
        output = directory / f"fixture-{i}.step"
        result = subprocess.run(
            [
                cli_path(),
                "pcb",
                "export",
                "step",
                "--force",
                "--subst-models",
                "--no-extra-pad-thickness",
                "--user-origin",
                "0x0mm",
                "--output",
                str(output),
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode or not output.exists():
            debug = root / "test-results"
            debug.mkdir(exist_ok=True)
            (debug / "alignment-failed.kicad_pcb").write_text(source.read_text())
            raise RuntimeError(result.stdout + result.stderr)
    node = root / "scripts/check_alignment.mjs"
    result = subprocess.run(
        [
            "node",
            str(node),
            str(model),
            str(directory / "fixture-0.step"),
            str(directory / "fixture-1.step"),
            json.dumps(transforms[1]),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stderr)
