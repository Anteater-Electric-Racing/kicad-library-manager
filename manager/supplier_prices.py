"""Parse explicit unit-price tables, including browser line-per-cell clipboard text."""

import re
from decimal import Decimal

CURRENCIES = "USD EUR GBP CAD AUD JPY CNY CHF HKD SGD NZD SEK NOK DKK PLN INR".split()


def parse_price(value):
    value = re.sub(r"\s+", " ", str(value)).strip()
    codes = "|".join(CURRENCIES)
    m = re.fullmatch(
        rf"(?:(?P<before>{codes})\s*)?(?P<symbol>US\$|CA\$|AU\$|\$|€|£)?\s*(?P<number>\d+(?:,\d{{3}})*(?:\.\d+)?)(?:\s*(?P<after>{codes}))?(?:\s*/\s*(?:ea|each|pc))?",
        value,
        re.I,
    )
    if not m:
        return None
    before, after = (m["before"] or "").upper(), (m["after"] or "").upper()
    if before and after and before != after:
        return None
    currency = (
        before
        or after
        or {"€": "EUR", "£": "GBP", "US$": "USD", "CA$": "CAD", "AU$": "AUD"}.get(
            m["symbol"], ""
        )
    )
    return format(Decimal(m["number"].replace(",", "")), "f"), currency


def header(value):
    return re.sub(r"[^a-z]", "", value.lower())


def quantity(value):
    value = value.strip().replace(",", "")
    if re.fullmatch(r"\d+\+?", value) and int(value.rstrip("+")) > 0:
        return str(int(value.rstrip("+")))
    return None


def table_price(rows):
    candidates = []
    qi = pi = width = None
    for cells in rows:
        normalized = [header(c) for c in cells]
        quantity_headers = {"quantity", "qty", "qtyunits"}
        price_headers = {
            "unitprice",
            "unitpriceusd",
            "unitpriceeur",
            "priceeach",
            "priceusd",
            "priceeur",
        }
        qs = [i for i, c in enumerate(normalized) if c in quantity_headers]
        ps = [i for i, c in enumerate(normalized) if c in price_headers]
        if qs and ps:
            qi, pi, width = qs[0], ps[0], len(cells)
            continue
        if all(re.fullmatch(r"[-: ]+", c) for c in cells):
            continue
        if qi is None:
            continue
        if len(cells) != width:
            qi = None
            continue
        q = quantity(cells[qi])
        p = parse_price(cells[pi])
        if not q or not p:
            qi = None
            continue
        candidates.append((int(q), p[0], p[1]))
    return candidates


def extract_price(text, html_rows=()):
    candidates = table_price(html_rows)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = []
    for line in lines:
        cells = re.split(r"\t+|\s*\|\s*| {2,}", line.strip("| "))
        if len(cells) == 1 and re.match(r"^\d[\d,]*\+?\s+", line):
            # Space-delimited quantity, unit price and optional extended price.
            m = re.fullmatch(
                r"(\d[\d,]*\+?)\s+((?:(?:USD|EUR|GBP)\s+)?[$€£]?\d[\d,.]*(?:\s+(?:USD|EUR|GBP))?)(?:\s+(.+))?",
                line,
            )
            if m:
                cells = [m[1], m[2]] + ([m[3]] if m[3] else [])
        rows.append(cells)
    candidates += table_price(rows)
    # Browser copies mix line breaks and tabs: a quantity may occupy its own
    # line while unit/extended prices share the next. Scan logical cells.
    cells = [cell for row in rows for cell in row]
    for i in range(len(cells) - 1):
        if header(cells[i]) not in ("quantity", "qty"):
            continue
        if header(cells[i + 1]) not in (
            "unitprice",
            "priceeach",
            "unitpriceusd",
            "unitpriceeur",
        ):
            continue
        start = i + 2
        width = 2
        if start < len(cells) and header(cells[start]) in (
            "extprice",
            "extendedprice",
            "totalprice",
            "subtotal",
        ):
            start += 1
            width = 3
        j = start
        while j + width <= len(cells):
            q = quantity(cells[j])
            p = parse_price(cells[j + 1])
            if not q or not p:
                break
            if width == 3 and not parse_price(cells[j + 2]):
                break
            candidates.append((int(q), p[0], p[1]))
            j += width
    if not candidates:
        return {}
    # Prefer the smallest purchasable quantity, not a full-reel tier seen first.
    q, price, currency = min(candidates, key=lambda x: x[0])
    if not currency:
        m = re.search(
            r"(?:prices? (?:are )?in|currency[:\s]+|unit price\s*\()\s*("
            + "|".join(CURRENCIES)
            + r")\b",
            text,
            re.I,
        )
        if m:
            currency = m[1].upper()
    return dict(UnitPrice=price, PriceCurrency=currency, PriceQuantity=str(q))
