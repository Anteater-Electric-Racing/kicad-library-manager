"""Model inspection and conservative, reviewed connector transformations."""

from __future__ import annotations

import copy
import math
import re
from .sexpr import Quoted as Q, parse, dump, children, child, value, property_set


def numeric_key(text):
    return (0, int(text)) if str(text).isdigit() else (1, str(text))


def symbols(text):
    tree = parse(text)
    if tree[0] != "kicad_symbol_lib":
        raise ValueError("A modern .kicad_sym library is required")
    return [str(n[1]) for n in children(tree, "symbol")]


def symbol_choices(text):
    """Prefer a unique leaf definition, never a nested graphical unit."""
    definitions = children(parse(text), "symbol")
    parents = {str(value(n, "extends")) for n in definitions if value(n, "extends")}
    leaves = [str(n[1]) for n in definitions if str(n[1]) not in parents]
    return leaves


def symbol_metadata(node, identity_node=None):
    props = {
        str(p[1]).casefold().replace("_", " "): str(p[2])
        for p in children(node, "property")
    }
    own = {
        str(p[1]).casefold().replace("_", " "): str(p[2])
        for p in children(
            identity_node if identity_node is not None else node, "property"
        )
    }
    return dict(
        MPN=own.get("manufacturer part number") or own.get("mpn") or str(node[1]),
        Manufacturer=props.get("manufacturer name") or props.get("manufacturer", ""),
        Description=props.get("ki description", ""),
        Datasheet=props.get("datasheet", ""),
        Reference=props.get("reference", ""),
    )


def flatten_symbol(text, name):
    tree = parse(text)
    definitions = {str(n[1]): n for n in children(tree, "symbol")}

    def resolve(current, seen):
        if current in seen or current not in definitions:
            raise ValueError("Missing or cyclic symbol inheritance")
        node = copy.deepcopy(definitions[current])
        parent = value(node, "extends")
        if parent:
            base = resolve(parent, seen | {current})
            node.extend(
                copy.deepcopy(item)
                for item in base[2:]
                if isinstance(item, list)
                and item
                and item[0]
                in {
                    "pin",
                    "rectangle",
                    "polyline",
                    "circle",
                    "arc",
                    "text",
                    "text_box",
                    "bezier",
                }
            )
            for item in children(base, "symbol"):
                if str(item[1]).startswith(parent + "_"):
                    item[1] = Q(current + str(item[1])[len(parent) :])
                node.append(item)
            own_props = {p[1] for p in children(node, "property")}
            node.extend(p for p in children(base, "property") if p[1] not in own_props)
            for tag in (
                "pin_names",
                "pin_numbers",
                "in_bom",
                "on_board",
                "body_styles",
            ):
                if not child(node, tag) and child(base, tag):
                    node.append(child(base, tag))
            node = [
                n for n in node if not (isinstance(n, list) and n and n[0] == "extends")
            ]
        return node

    return resolve(name, set())


def symbol_pins(node):
    result = []
    # Some supplier libraries (including SamacSys) put pins at the top level.
    # KiCad accepts these as unit 1, body style 1.
    for unit in [node, *children(node, "symbol")]:
        for pin in children(unit, "pin"):
            at = child(pin, "at", ["at", "0", "0", "0"])
            result.append(
                dict(
                    number=str(value(pin, "number")),
                    name=str(value(pin, "name")),
                    type=str(pin[1]),
                    x=float(at[1]),
                    y=float(at[2]),
                    angle=float(at[3]),
                    length=float(value(pin, "length", 2.54)),
                    unit=str(unit[1]) if unit is not node else str(node[1]) + "_1_1",
                    hidden="hide" in pin,
                )
            )
    return result


def footprint_data(text):
    node = parse(text)
    if node[0] not in ("footprint", "module"):
        raise ValueError("A .kicad_mod footprint is required")
    pads = []
    for i, pad in enumerate(children(node, "pad")):
        at = child(pad, "at", ["at", "0", "0"])
        size = child(pad, "size", ["size", "1", "1"])
        drill = child(pad, "drill", ["drill", "0"])
        diameter = next(
            (
                float(x)
                for x in drill[1:]
                if not isinstance(x, list) and str(x).replace(".", "", 1).isdigit()
            ),
            0,
        )
        dimensions = [
            float(x)
            for x in drill[1:]
            if not isinstance(x, list) and re.fullmatch(r"\d+(?:\.\d*)?|\.\d+", str(x))
        ]
        offset = child(drill, "offset", ["offset", "0", "0"])
        pads.append(
            dict(
                index=i,
                number=str(pad[1]),
                type=pad[2],
                shape=pad[3],
                x=float(at[1]),
                y=float(at[2]),
                angle=float(at[3]) if len(at) > 3 else 0,
                width=float(size[1]),
                height=float(size[2]),
                drill=diameter,
                drillWidth=dimensions[0] if dimensions else 0,
                drillHeight=dimensions[1] if len(dimensions) > 1 else diameter,
                drillOffset=[float(x) for x in offset[1:3]],
                roundrectRatio=float(value(pad, "roundrect_rratio", 0.25)),
                layers=[str(x) for x in child(pad, "layers", ["layers"])[1:]],
            )
        )
    lines = []
    for line in children(node, "fp_line"):
        start, end = child(line, "start"), child(line, "end")
        if start and end:
            lines.append(
                dict(
                    start=[float(v) for v in start[1:3]],
                    end=[float(v) for v in end[1:3]],
                    layer=value(line, "layer"),
                )
            )
    models = []
    for model in children(node, "model"):
        transform = {}
        for tag, default in [
            ("offset", [0, 0, 0]),
            ("rotate", [0, 0, 0]),
            ("scale", [1, 1, 1]),
        ]:
            xyz = child(child(model, tag, []), "xyz")
            transform[tag] = [float(x) for x in xyz[1:4]] if xyz else default
        if child(model, "offset") is None:
            legacy = child(child(model, "at", []), "xyz")
            if legacy:
                transform["offset"] = [float(x) * 25.4 for x in legacy[1:4]]
        models.append(dict(path=str(model[1]), **transform))
    return dict(name=str(node[1]), pads=pads, lines=lines, models=models)


def infer_connector(footprint, pins=None):
    """Evidence-based proposal; no geometrical pad classification."""
    pins = pins or []
    electrical = sorted(
        {
            p["number"]
            for p in footprint["pads"]
            if p["number"] and p["type"] != "np_thru_hole"
        },
        key=numeric_key,
    )
    original = sorted({p["number"] for p in pins}, key=numeric_key)
    shield = [
        p["number"]
        for p in pins
        if re.search(r"\b(shield|shell|case|chassis)\b", p["name"], re.I)
    ]
    suspicious = [n for n in electrical if not n.isdigit()]
    suspicious += [
        p["number"]
        for p in footprint["pads"]
        if p["type"] == "np_thru_hole" and p["number"]
    ]
    reasons = []
    if shield:
        reasons.append("Shield/case pins identified: " + ", ".join(shield))
    if suspicious:
        reasons.append(
            "Review named or numbered mounting pads: "
            + ", ".join(sorted(set(suspicious)))
        )
    if pins and original != electrical:
        reasons.append(
            "Original symbol numbers and electrical footprint numbers differ"
        )
    if not 1 <= len(electrical) <= 24:
        reasons.append("Generic connector layouts support 1–24 electrical connections")
    if electrical != [str(i) for i in range(1, len(electrical) + 1)]:
        reasons.append(
            "Generic library requires an explicitly reviewed consecutive 1–N pin set"
        )
    units = {p["unit"].rsplit("_", 2)[-2] for p in pins}
    if len(units - {"0", "1"}) or len(pins) != len(original):
        reasons.append(
            "Multi-unit, alternate-body or repeated symbol pins need the supplied symbol"
        )
    return dict(
        numbers=electrical,
        count=len(electrical),
        originalNumbers=original,
        shield=shield,
        mountingHoles=sum(
            p["type"] == "np_thru_hole" and not p["number"] for p in footprint["pads"]
        ),
        reasons=reasons,
        eligible=not reasons,
        requiresConfirmation=True,
        evidence="original symbol + footprint"
        if pins
        else "footprint only; confirm contact identities",
    )


def connector_symbol(count, layout="single", pins=None, name=None):
    if not 1 <= count <= 24 or layout not in ("single", "split"):
        raise ValueError("Unsupported connector layout")
    name = name or f"Connector_{count:02d}_{layout}"
    original = {p["number"]: p for p in (pins or [])}
    rows = count if layout == "single" else math.ceil(count / 2)
    height = (rows + 1) * 2.54
    meaningful_names = [
        p["name"] for p in (pins or []) if p["name"] not in ("", "~", p["number"])
    ]
    half_width = max(
        2.54, max((len(n) * 0.8 + 1.27 for n in meaningful_names), default=0)
    )
    body = [
        "symbol",
        Q(name + "_0_1"),
        [
            "rectangle",
            ["start", str(-half_width), str(height / 2)],
            ["end", str(half_width), str(-height / 2)],
            ["stroke", ["width", "0.254"], ["type", "default"]],
            ["fill", ["type", "background"]],
        ],
    ]
    unit = ["symbol", Q(name + "_1_1")]
    for i in range(1, count + 1):
        right = layout == "split" and i % 2 == 0
        row = i - 1 if layout == "single" else (i - 1) // 2
        p = original.get(str(i), {})
        unit.append(
            [
                "pin",
                p.get("type", "passive"),
                "line",
                [
                    "at",
                    str(half_width + 2.54 if right else -half_width - 2.54),
                    str((rows - 1) * 1.27 - row * 2.54),
                    "180" if right else "0",
                ],
                ["length", "2.54"],
                [
                    "name",
                    Q(p.get("name", str(i))),
                    ["effects", ["font", ["size", "1.27", "1.27"]]],
                ],
                ["number", Q(str(i)), ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ]
        )
    pin_names = ["pin_names", ["offset", "1.016"]]
    if not meaningful_names:
        pin_names.append("hide")
    node = [
        "symbol",
        Q(name),
        pin_names,
        ["in_bom", "yes"],
        ["on_board", "yes"],
        body,
        unit,
    ]
    property_set(node, "Reference", "J", True)
    property_set(node, "Value", name, True)
    for prop in children(node, "property"):
        if prop[1] == "Reference":
            child(prop, "at")[2] = str(height / 2 + 2.54)
        if prop[1] == "Value":
            child(prop, "at")[2] = str(-height / 2 - 2.54)
    return node


def connector_body_styles(count, layout="single", pins=None, name=None):
    """Store both representations on the same KiCad part using body styles 1/2."""
    node = connector_symbol(count, layout, pins, name)
    other = connector_symbol(
        count, "split" if layout == "single" else "single", pins, str(node[1])
    )
    for unit in children(other, "symbol"):
        unit[1] = Q(str(unit[1]).rsplit("_", 1)[0] + "_2")
        node.append(unit)
    return node


def symbol_library(node, name, properties=None):
    node = copy.deepcopy(node)
    old = str(node[1])
    node[1] = Q(name)
    for unit in children(node, "symbol"):
        if str(unit[1]).startswith(old + "_"):
            unit[1] = Q(name + str(unit[1])[len(old) :])
    for key, val in (properties or {}).items():
        property_set(node, key, str(val))
    return (
        dump(
            [
                "kicad_symbol_lib",
                ["version", "20241209"],
                ["generator", "kicad_library_manager"],
                node,
            ]
        )
        + "\n"
    )


def _model_transform_nodes(transform):
    result = []
    for tag in ("offset", "rotate", "scale"):
        values = transform.get(tag)
        if (
            not isinstance(values, list)
            or len(values) != 3
            or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in values)
        ):
            raise ValueError(
                "Model transform must contain three finite values per axis group"
            )
        if tag == "scale" and not all(v > 0 for v in values):
            raise ValueError("Model scale must be positive")
        result.append([tag, ["xyz", *[format(v, ".12g") for v in values]]])
    return result


def footprint_payload(
    text,
    name,
    model_path=None,
    transform=None,
    *,
    preserve_models=False,
    transform_model_index=None,
    path_moves=None,
):
    node = parse(text)
    node[1] = Q(name)
    if preserve_models:
        models = children(node, "model")
        if transform_model_index is not None and transform is not None:
            if not 0 <= transform_model_index < len(models):
                raise ValueError("The selected model reference no longer exists")
            model = models[transform_model_index]
            # KiCad's historical 'at' form is inches. A changed transform is
            # written as an explicit millimeter offset; untouched nodes stay exact.
            model[:] = [
                n
                for n in model
                if not (
                    isinstance(n, list)
                    and n
                    and n[0] in ("offset", "at", "rotate", "scale")
                )
            ]
            model.extend(_model_transform_nodes(transform))
        for model in models:
            for old, new in sorted(
                (path_moves or {}).items(), key=lambda item: -len(item[0])
            ):
                prefix = "${MYCO_PARTS_DIR}/../" + old + "/"
                if str(model[1]).startswith(prefix):
                    model[1] = Q(
                        "${MYCO_PARTS_DIR}/../"
                        + new
                        + "/"
                        + str(model[1])[len(prefix) :]
                    )
                    break
    elif model_path:
        node = [n for n in node if not (isinstance(n, list) and n and n[0] == "model")]
        transform = transform or dict(
            offset=[0, 0, 0], rotate=[0, 0, 0], scale=[1, 1, 1]
        )
        node.append(["model", Q(model_path), *_model_transform_nodes(transform)])
    elif children(node, "model"):
        node = [n for n in node if not (isinstance(n, list) and n and n[0] == "model")]
    return dump(node) + "\n"
