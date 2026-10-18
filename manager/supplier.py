"""Supplier metadata extraction, adapted from the retired importer. No library writes."""

from datetime import datetime, timezone
from .supplier_prices import parse_price, extract_price
from html.parser import HTMLParser
import json
from io import BytesIO
import re
from urllib.parse import urlparse, unquote, quote
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

MAX_PAGE_BYTES = 8 * 1024 * 1024


def clean(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _distributor(url):
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    suffixes = "com ca de co.uk fr it es nl be at ch dk se no fi pl cz ie pt hu ro sk gr jp cn hk tw kr in sg my ph th au com.au co.nz co.za mx com.mx br".split()
    for brand, label in [("digikey", "DigiKey"), ("mouser", "Mouser")]:
        domains = [brand + "." + s for s in suffixes]
        if (
            p.scheme == "https"
            and not p.username
            and not p.password
            and p.port in (None, 443)
            and any(host == d or host == "www." + d for d in domains)
        ):
            if (
                ("/products/detail/" in p.path or "/product-detail/" in p.path)
                if brand == "digikey"
                else ("/productdetail/" in p.path.lower())
            ):
                return label
    raise ValueError("Enter an HTTPS DigiKey or Mouser product-detail URL.")


def normalize_url(url):
    """Accept browser-address-bar copies without a scheme; retain host validation."""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url
    _distributor(url)
    return url


def distributor(url):
    return _distributor(normalize_url(url))


def clipboard_is_url(content):
    """Only a single address takes the network path, never a whole page."""
    content = content.strip()
    return bool(
        content
        and not re.search(r"\s", content)
        and (
            re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://|//", content)
            or re.match(r"(?:www\.)?(?:digikey|mouser)\.", content, re.I)
        )
    )


class PageReadError(ValueError):
    """A valid URL could not be retrieved; offer the browser-copy workflow."""


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        distributor(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    url = normalize_url(url)
    try:
        with build_opener(SafeRedirect()).open(
            Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ),
            timeout=25,
        ) as response:
            payload = response.read(MAX_PAGE_BYTES + 1)
            if len(payload) > MAX_PAGE_BYTES:
                raise ValueError("Product page exceeds 8 MiB.")
            content = payload.decode("utf-8", errors="replace")
            if re.search(
                r"<title[^>]*>[^<]*(?:access denied|robot|just a moment|pardon our interruption)",
                content,
                re.I,
            ):
                raise PageReadError(
                    distributor(url)
                    + " requires a browser check. Use Open URL in browser, then copy the product details."
                )
            return content
    except PageReadError:
        raise
    except HTTPError as exc:
        exc.close()
        if exc.code in (403, 429):
            raise PageReadError(
                distributor(url)
                + " blocked automatic reading (HTTP "
                + str(exc.code)
                + "). Open the page in your browser, copy its product identity and specifications, then use Import from clipboard."
            ) from exc
        raise PageReadError(
            "Could not read the product page (HTTP "
            + str(exc.code)
            + "). Use the browser-copy option below."
        ) from exc
    except Exception as exc:
        raise PageReadError(
            "Could not read this product page. Open it in your browser, then paste its product details below and click Read pasted details. "
            + str(exc)
        ) from exc


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.scripts = []
        self.script = None
        self.skip = 0
        self.links = []
        self.href = ""
        self.link_text = []
        self.cells = []
        self.cell = None
        self.rows = []
        self.table_row = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.table_row = []
        if tag in ("td", "th", "dt", "dd"):
            self.cell = []
        if tag == "script":
            self.script = []
        if tag == "style":
            self.skip += 1
        if tag in (
            "td",
            "th",
            "tr",
            "div",
            "p",
            "br",
            "li",
            "dt",
            "dd",
            "h1",
            "h2",
            "span",
        ):
            self.lines.append("\n")
        if tag == "a":
            self.href = attrs.get("href", "")
            self.link_text = []

    def handle_endtag(self, tag):
        if tag in ("td", "th", "dt", "dd") and self.cell is not None:
            value = clean(" ".join(self.cell))
            self.cells.append(value)
            if self.table_row is not None:
                self.table_row.append(value)
            self.cell = None
        if tag == "tr" and self.table_row is not None:
            self.rows.append(self.table_row)
            self.table_row = None
        if tag == "script" and self.script is not None:
            self.scripts.append("".join(self.script))
            self.script = None
        if tag == "style":
            self.skip = max(0, self.skip - 1)
        if tag in ("td", "th", "tr", "div", "p", "li", "dt", "dd", "span"):
            self.lines.append("\n")
        if tag == "a":
            self.links.append((self.href, clean("".join(self.link_text))))
            self.href = ""

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        elif not self.skip:
            self.lines.append(data)
            if self.cell is not None:
                self.cell.append(data)
            if self.href:
                self.link_text.append(data)


ALIASES = {
    "MPN": [
        "Manufacturer Product Number",
        "Manufacturer Part Number",
        "Mfr. Part #",
        "Mfr Part #",
        "Mfr. #",
    ],
    "Manufacturer": ["Manufacturer", "Mfr", "Supplier"],
    "Description": ["Detailed Description", "Description"],
    "Distributor_PN": ["DigiKey Part Number", "Mouser Part #", "Mouser #"],
    "PriceCurrency": ["Currency", "Price Currency"],
    "Resistance": ["Resistance"],
    "Capacitance": ["Capacitance"],
    "Tolerance": ["Tolerance", "Resistance Tolerance"],
    "Package": [
        "Package / Case",
        "Case Code - in",
        "Package Case",
        "Case Code - inch",
        "Chip Size",
    ],
    "MetricPackage": ["Case Code - mm"],
    "Terminations": ["Number of Terminations", "Number of Pins"],
    "Polarization": ["Polarization"],
    "Voltage_VDC": [
        "Voltage - Rated",
        "Voltage Rating DC",
        "Voltage Rating",
        "Voltage DC",
    ],
    "Current_A": ["Current Rating (Amps)", "Current Rating", "Rated Current"],
    "Voltage_V": ["Voltage Rating", "Voltage - Rated", "Rated Voltage"],
    "Power_W": ["Power (Watts)", "Power Rating", "Power Dissipation", "Power"],
    "Dielectric": ["Dielectric", "Temperature Coefficient", "Temp. Coefficient"],
    "TemperatureCoefficient": ["Temperature Coefficient", "Temp. Coefficient"],
    "OperatingTemperature": ["Operating Temperature", "Temperature Range"],
    "MinimumTemperature": ["Minimum Operating Temperature"],
    "MaximumTemperature": ["Maximum Operating Temperature"],
    "Composition": ["Composition", "Technology"],
    "ESR": ["ESR (Equivalent Series Resistance)", "ESR"],
    "RippleCurrent": ["Ripple Current", "Ripple Current - Low Frequency"],
    "Qualification": ["Ratings", "Qualification"],
    "MountingType": ["Mounting Type", "Termination Style"],
    "Datasheet": ["Datasheet", "Datasheets"],
    "DistributorStock": ["In Stock", "In-Stock", "Quantity Available", "Availability"],
}


def extract(content, expected_mpn=""):
    page = Page()
    page.feed(content)
    pairs = {}
    offers = []

    # Structured product data and named product attributes embedded in page state.
    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            values = {key(k): v for k, v in node.items()}
            mpn = (
                values.get("mpn")
                or values.get("manufacturerproductnumber")
                or values.get("manufacturerpartnumber")
            )
            # Related-product cards often precede the selected product in page state.
            if expected_mpn and mpn and str(mpn).casefold() != expected_mpn.casefold():
                return
            name = (
                values.get("name") or values.get("label") or values.get("parametertext")
            )
            value = values.get("value", values.get("valuetext"))
            if isinstance(name, str) and isinstance(value, (str, int, float)):
                pairs.setdefault(key(name), clean(value))
            if values.get("type") == "Product" or mpn:
                product_offers = values.get("offers", [])
                if isinstance(product_offers, dict):
                    product_offers = [product_offers]
                if isinstance(product_offers, list):
                    offers.extend(
                        o
                        for o in product_offers
                        if isinstance(o, dict)
                        and o.get("@type") == "Offer"
                        and "price" in o
                    )
                for source, dest in [
                    ("manufacturerproductnumber", "MPN"),
                    ("manufacturerpartnumber", "MPN"),
                    ("mpn", "MPN"),
                    ("description", "Description"),
                    ("sku", "Distributor_PN"),
                    ("datasheeturl", "Datasheet"),
                ]:
                    item = values.get(source)
                    if isinstance(item, dict):
                        item = item.get("DetailedDescription") or item.get(
                            "ProductDescription"
                        )
                    if isinstance(item, (str, int, float)):
                        pairs.setdefault(key(dest), clean(item))
                brand = values.get("manufacturer") or values.get("brand")
                if isinstance(brand, dict):
                    brand = brand.get("name") or brand.get("Name")
                if isinstance(brand, str):
                    pairs.setdefault("manufacturer", brand)
            for item in node.values():
                walk(item)

    for script in page.scripts:
        try:
            walk(json.loads(script))
        except (ValueError, RecursionError):
            pass
    if content.lstrip().startswith(("{", "[")):
        try:
            walk(json.loads(content))
        except (ValueError, RecursionError):
            pass
    text = "".join(page.lines) if "<" in content and ">" in content else content
    lines = [line.strip() for line in text.splitlines() if clean(line)]
    lookup = {
        key(a): field for field, names in ALIASES.items() for a in [field, *names]
    }
    for i, cell in enumerate(page.cells[:-1]):
        label = key(cell.rstrip(":"))
        if label in lookup and key(page.cells[i + 1].rstrip(":")) not in lookup:
            pairs.setdefault(label, page.cells[i + 1])
    for i, line in enumerate(lines):
        # Also accept browser clipboard tables (tabs), colon-separated attributes.
        columns = re.split(r"\t+|\s*\|\s*|:\s*", line, maxsplit=1)
        label = key(columns[0].rstrip(":"))
        if label in lookup:
            value = (
                columns[1]
                if len(columns) == 2 and columns[1]
                else (
                    lines[i + 1]
                    if i + 1 < len(lines) and key(lines[i + 1]) not in lookup
                    else ""
                )
            )
            if value:
                pairs.setdefault(label, clean(value))
    result = {}
    for field, aliases in ALIASES.items():
        result[field] = next(
            (pairs[key(a)] for a in [field] + aliases if pairs.get(key(a))), ""
        )
    for href, label in page.links:
        if "datasheet" in label.lower() and href.startswith("https://"):
            result["Datasheet"] = href
            break
    stock = re.search(
        r"(?:In[ -]Stock\s*:?\s*([\d,]+)|([\d,]+)\s+In Stock)", text, re.I
    )
    if stock:
        result["DistributorStock"] = stock[1] or stock[2]
    result.update(extract_price(text, page.rows))
    if not result.get("UnitPrice"):
        for offer in offers:
            price = parse_price(str(offer["price"]))
            if price:
                result.update(
                    UnitPrice=price[0],
                    PriceCurrency=offer.get("priceCurrency", ""),
                    PriceQuantity="",
                )
                break
    if result.get("UnitPrice"):
        if not result.get("PriceCurrency"):
            currency = re.search(
                r"(?:prices? (?:are )?in|currency[: ]+)\s*(USD|EUR|GBP|CAD|AUD|JPY|CNY|CHF|HKD|SGD)",
                text,
                re.I,
            )
            if currency:
                result["PriceCurrency"] = currency[1].upper()
        result["PriceCheckedUTC"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
    return result


def url_identity(url):
    """Read the identity carried by product URLs, without guessing specifications."""
    url = normalize_url(url)
    path = urlparse(url).path
    if distributor(url) == "DigiKey":
        match = re.search(
            r"/(?:products/detail|product-detail)/([^/]+)/([^/]+)/[^/]+/?$", path, re.I
        )
    else:
        match = re.search(r"/productdetail/([^/]+)/([^/]+)/?$", path, re.I)
    if not match:
        return {}
    manufacturer, mpn = (unquote(v) for v in match.groups())
    if any(ord(c) < 32 for c in manufacturer + mpn) or len(mpn) > 200:
        return {}
    return {
        "MPN": mpn,
        "Manufacturer": {"yageo": "YAGEO", "kemet": "KEMET"}.get(
            manufacturer.lower(), manufacturer.replace("-", " ")
        ),
    }


class ManufacturerRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if not (
            parsed.scheme == "https"
            and parsed.hostname in ("yageogroup.com", "www.yageogroup.com")
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
        ):
            raise ValueError("Manufacturer lookup redirected outside its official site")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _manufacturer_document(url):
    try:
        with build_opener(ManufacturerRedirect()).open(
            Request(
                url,
                headers={
                    "User-Agent": "KiCad-Library-Manager/0.1",
                    "Accept": "application/pdf",
                },
            ),
            timeout=20,
        ) as response:
            payload = response.read(MAX_PAGE_BYTES + 1)
    except HTTPError as exc:
        exc.close()
        raise
    if len(payload) > MAX_PAGE_BYTES or not payload.startswith(b"%PDF-"):
        raise ValueError("Manufacturer did not return a supported PDF specification")
    return payload


def _specsheet_text(payload):
    from . import _vendor  # noqa: F401 -- activates the bundled dependency path
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(payload))
    if reader.is_encrypted or not 0 < len(reader.pages) <= 5:
        raise ValueError("Manufacturer specsheet is not a short public PDF")
    return "\n".join(
        page.extract_text(extraction_mode="layout") or "" for page in reader.pages
    ).replace("\u200b", "")


def _yageo_specsheet(identity):
    """Use the manufacturer's exact-part document, never decode a guessed series."""
    mpn = identity["MPN"]
    url = (
        "https://www.yageogroup.com/component-documentation/download/specsheet/"
        + quote(mpn, safe="")
    )
    text = _specsheet_text(_manufacturer_document(url))
    lines = [clean(line) for line in text.splitlines() if clean(line)]
    # The document header must name this exact part or list it as a formal alias.
    header = lines[:5]
    aliases = []
    for line in header:
        match = re.fullmatch(r"Aliases \((.+)\)", line)
        if match:
            aliases.extend(clean(item) for item in match[1].split(","))
    if not header or mpn.casefold() not in {
        item.casefold() for item in [header[0], *aliases]
    }:
        raise ValueError("Manufacturer document does not identify the requested part")
    parsed = extract(text)
    parsed.update(MPN=mpn, Manufacturer=identity["Manufacturer"], Datasheet=url)
    package = re.search(r"Case Code\s+\(EIA / mm\)\s+(\d{4})\s*/\s*(\d{4})", text)
    if package:
        parsed.update(Package=package[1], MetricPackage=package[2])
    # PDF extraction places table labels and values together on one line.
    labels = {
        "Resistance": r"Resistance[ \t]+(?!Tolerance)([^\n]+)",
        "Capacitance": r"Capacitance[ \t]+([^\n]+)",
        "Tolerance": r"(?:Resistance Tolerance|Tolerance)[ \t]+([^\n]+)",
        "Power_W": r"Power[ \t]+([^\n]+)",
        "Voltage_VDC": r"Voltage DC[ \t]+([^\n]+)",
        "TemperatureCoefficient": r"Temp\. Coefficient[ \t]+([^\n]+)",
        "OperatingTemperature": r"Temperature Range[ \t]+([^\n]+)",
        "Package": r"Chip Size[ \t]+(\d{4})\b",
    }
    for field, pattern in labels.items():
        match = re.search(r"(?m)(?:^|[ \t]{2,})" + pattern, text)
        if match:
            parsed[field] = clean(re.split(r"\s{2,}", match[1].strip())[0])
    # Preserve the manufacturer summary as a readable description.
    if len(lines) > 1:
        parsed["Description"] = (
            lines[2]
            if lines[1].startswith("Aliases (") and len(lines) > 2
            else lines[1]
        )
    if not (parsed.get("Resistance") or parsed.get("Capacitance")):
        raise ValueError("Manufacturer document did not expose passive specifications")
    if parsed.get("Capacitance") and re.fullmatch(
        r"C0G|NP0|U2J|[XYZ][4-9][A-Z]", parsed.get("TemperatureCoefficient", "")
    ):
        parsed["Dielectric"] = parsed["TemperatureCoefficient"]
    return parsed, url


def _normalize_product(part):
    """Keep field values usable by the importer without inventing missing data."""
    if part.get("Resistance") and not part.get("Capacitance"):
        part.update(Type="resistor", Value=part["Resistance"])
    if part.get("Capacitance") and not part.get("Resistance"):
        part.update(Type="capacitor", Value=part["Capacitance"])
    for field, unit in [("Power_W", "W"), ("Voltage_VDC", "V")]:
        # Supplier pages often append equivalent fractions or test conditions.
        match = re.match(
            r"^(\d+(?:\.\d+)?)\s*([munµk]?)\s*" + unit + r"(?:DC)?(?=\s*(?:,|\(|$))",
            part.get(field, ""),
        )
        if match:
            part[field] = match[1] + match[2] + unit
    from .passives import package_code

    package = package_code(part.get("Package", ""), part.get("MetricPackage", ""))
    if package:
        part["Package"] = package
    return part


def read_product(url="", content=""):
    """Read supplier metadata, then an exact manufacturer source when blocked.

    The returned provenance distinguishes page data, manufacturer data and URL
    identity. Callers should display warnings; partial identity is not a claim
    that ratings, availability or pricing were retrieved.
    """
    if not url and clipboard_is_url(content):
        url, content = content, ""
    url = normalize_url(url) if url else ""
    identity = url_identity(url) if url else {}
    warnings = []
    provenance = {"method": "pasted-details", "url": url}
    if not content:
        if not url:
            raise ValueError("Paste a product URL or copied product details")
        try:
            content = fetch(url)
            provenance["method"] = "supplier-page"
        except PageReadError as exc:
            warnings.append(str(exc))
    part = (
        {
            field: value
            for field, value in extract(content, identity.get("MPN", "")).items()
            if value
        }
        if content
        else {}
    )
    if (
        identity.get("MPN")
        and part.get("MPN")
        and identity["MPN"].casefold() != part["MPN"].casefold()
    ):
        warnings.append(
            "The product details name a different part number from the URL. Check the part number before saving."
        )
    usable = any(
        part.get(field) for field in ("Resistance", "Capacitance", "Description")
    )
    if not usable and identity.get("Manufacturer") in ("YAGEO", "KEMET"):
        try:
            part, source_url = _yageo_specsheet(identity)
            provenance = {"method": "manufacturer-specsheet", "url": source_url}
            warnings = [
                distributor(url)
                + " page data was unavailable. Specifications came from the exact-part "
                "YAGEO Group document; supplier price and stock were not imported."
            ]
        except Exception as exc:
            # Unsupported/missing documents must never fabricate series ratings.
            warnings.append(
                "The manufacturer lookup could not supply exact specifications: "
                + str(exc)
            )
    if not part:
        if not identity:
            raise PageReadError(
                "No product information could be read. Open the page and paste its product details."
            )
        part = dict(identity)
        provenance = {"method": "url-identity", "url": url}
        warnings.append(
            "Only manufacturer and part number were read from the URL. Paste the product details or enter the missing specifications."
        )
    else:
        for field, value in identity.items():
            part.setdefault(field, value)
            if not part.get(field):
                part[field] = value
    if url:
        part["SupplierURL"] = url
    _normalize_product(part)
    part = {field: value for field, value in part.items() if value}
    provenance["fields"] = [field for field, value in part.items() if value]
    return {"part": part, "warnings": warnings, "provenance": provenance}
