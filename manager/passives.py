"""Explicit passive values and package-unit checks, independent of catalog identity."""

from decimal import Decimal
import re

PACKAGES = {"0402": "1005", "0603": "1608", "0805": "2012", "1206": "3216"}


def package_code(value, metric=""):
    value = value.strip()
    match = re.fullmatch(r"(\d{4})\s*(?:metric|mm)", value, re.I)
    if match:
        metric = match[1]
        value = ""
    match = re.fullmatch(r"(\d{4})(?:\s*\((\d{4})\s*Metric\))?", value, re.I)
    if match:
        if match[2] and PACKAGES.get(match[1]) != match[2]:
            raise ValueError("Imperial and metric package sizes disagree")
        return match[1]
    if metric and not value:
        return next((p for p, m in PACKAGES.items() if m == metric.strip()), "")
    return ""


def normalize(row, metadata):
    kind = row["Type"]
    if metadata.get("Terminations") and str(metadata["Terminations"]).strip() != "2":
        raise ValueError(
            "A multi-terminal passive needs a bespoke symbol and footprint"
        )
    if re.search(
        r"\b(array|network|polarized|bipolar)\b", row["Description"], re.I
    ) or metadata.get("Polarization", "").lower() in ("polar", "polarized", "bipolar"):
        raise ValueError(
            "This passive needs specifically reviewed models; choose Import my models"
        )
    raw = (
        str(metadata.get("Value", ""))
        .strip()
        .replace("µ", "u")
        .replace("μ", "u")
        .replace("Ω", "Ohm")
        .replace(" ", "")
    )
    raw = (
        raw.replace("Ohms", "Ohm")
        .replace("ohms", "Ohm")
        .replace("kOhm", "k")
        .replace("MOhm", "M")
    )
    match = re.fullmatch(
        r"(\d+(?:\.\d*)?|\.\d+)([pnumkMGT]?)(?:Ohm|ohm|R)?"
        if kind == "resistor"
        else r"(\d+(?:\.\d*)?|\.\d+)([pnumkMGT]?)F?",
        raw,
    )
    if not match and kind == "resistor":
        embedded = re.fullmatch(r"(\d+)([RkM])(\d*)", raw)
        if embedded:
            raw = (
                embedded[1]
                + ("." + embedded[3] if embedded[3] else "")
                + ("" if embedded[2] == "R" else embedded[2])
            )
            match = re.fullmatch(r"(\d+(?:\.\d*)?)([pnumkMGT]?)", raw)
    if not match:
        raise ValueError(
            "Enter a numeric passive value, e.g. 10k or 100nF. SI prefixes are case-sensitive."
        )
    powers = {
        "p": -12,
        "n": -9,
        "u": -6,
        "m": -3,
        "": 0,
        "k": 3,
        "M": 6,
        "G": 9,
        "T": 12,
    }
    number = Decimal(match[1]) * Decimal(10) ** powers[match[2]]
    if not number and kind != "resistor":
        raise ValueError("Capacitance must be positive")
    exp = 0 if not number else number.adjusted() // 3 * 3
    if exp not in powers.values():
        raise ValueError("Value is outside the supported SI range")
    prefix = next(k for k, v in powers.items() if v == exp)
    numeric = (
        format(number / (Decimal(10) ** exp), "f").rstrip("0").rstrip(".")
        if "." in format(number / (Decimal(10) ** exp), "f")
        else format(number / (Decimal(10) ** exp), "f")
    )
    row["Value"] = numeric + prefix + ("F" if kind == "capacitor" else "")
    tolerance = row["Tolerance"].replace("±", "").replace("+/-", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)%", tolerance)
    if m:
        if not 0 < Decimal(m[1]) <= 100:
            raise ValueError("Tolerance must be greater than zero and at most 100%")
    elif not (
        kind == "capacitor"
        and re.fullmatch(r"(?:\d+(?:\.\d+)?)[pnuµ]F", tolerance)
        and Decimal(re.match(r"[\d.]+", tolerance)[0]) > 0
    ):
        raise ValueError(
            "Enter a percentage tolerance, or an absolute capacitance tolerance"
        )
    row["Tolerance"] = tolerance
    rating = "Power_W" if kind == "resistor" else "Voltage_VDC"
    raw = row[rating].strip()
    unit = "W" if kind == "resistor" else "V"
    frac = re.fullmatch(r"(\d+)\s*/\s*(\d+)\s*W?", raw)
    if frac and Decimal(frac[2]) != 0:
        raw = str(Decimal(frac[1]) / Decimal(frac[2]))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([munµk]?)\s*" + unit + r"?(?:DC)?", raw)
    if not m or Decimal(m[1]) <= 0:
        raise ValueError(
            "Enter a positive "
            + ("power" if kind == "resistor" else "voltage")
            + " rating"
        )
    row[rating] = format(
        Decimal(m[1])
        * Decimal(
            str(
                {
                    "": 1,
                    "m": 0.001,
                    "u": 0.000001,
                    "µ": 0.000001,
                    "n": 0.000000001,
                    "k": 1000,
                }[m[2]]
            )
        ),
        "f",
    )
    row["Package"] = package_code(row["Package"], metadata.get("MetricPackage", ""))
    if row["Package"] not in PACKAGES:
        raise ValueError(
            "Select 0402, 0603, 0805, or 1206 (imperial), or import a bespoke footprint"
        )
    return row
