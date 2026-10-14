"""InvestorGain report + detail page scraper. Python standard library only."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SOURCE = "https://www.investorgain.com/report/ipo-gmp-live/331/"


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, tag):
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    yield child
                yield from child.find(tag)

    def text(self):
        return " ".join("".join(c.text() if isinstance(c, Node) else c for c in self.children).split())


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag in self.VOID:
            self.stack[-1].children.append(" ")
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def number(text):
    match = re.search(r"(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?", text.replace("−", "-"))
    return float(match[0].replace(",", "")) if match else None


def positive(text):
    value = number(text)
    return value if value is not None and value > 0 else None


def percent(text):
    match = re.search(r"\(([+-]?[\d.]+)%\)", text)
    return float(match[1]) if match else None


def parse_report(html):
    doc = Document(html).root
    table = next((n for n in doc.find("table") if n.attrs.get("id") == "reportTable"), None)
    if table is None:
        raise ValueError("InvestorGain's IPO table was not found. The source layout may have changed.")
    rows, seen = [], set()
    for tr in table.find("tr"):
        cells = {td.attrs.get("data-label"): td for td in tr.find("td") if td.attrs.get("data-label")}
        name_cell = cells.get("Name")
        if name_cell is None:
            continue
        link = next((a for a in name_cell.find("a") if re.fullmatch(r"/gmp/[^/]+/\d+/", a.attrs.get("href", ""))), None)
        if link is None:
            continue
        url = urljoin(SOURCE, link.attrs["href"])
        if url in seen:
            continue
        seen.add(url)
        txt = lambda key: cells[key].text() if key in cells else ""
        badges = [n.text() for n in name_cell.find("span") if "badge" in n.attrs.get("class", "")]
        board = "SME" if any("SME" in b for b in badges) else "Mainboard" if "IPO" in badges else "Unknown"
        status = next(({"U": "Upcoming", "O": "Open", "CT": "Closing today", "C": "Closed", "L": "Listed"}[b] for b in badges if b in {"U", "O", "CT", "C", "L"}), None)
        if status is None:
            # Listed rows use a listing-price label instead of a status badge.
            status = "Listed" if "L@" in name_cell.text() or "data-cfemail" in str(name_cell.attrs) or any("data-cfemail" in a.attrs for a in name_cell.find("a")) else "Unknown"
        gmp_cell = cells.get("GMP")
        bold = next(gmp_cell.find("b"), None) if gmp_cell else None
        price, lot = positive(txt("Price (₹)")), positive(txt("Lot"))
        rows.append({
            "id": url.rstrip("/").split("/")[-1], "name": link.text(), "url": url,
            "board": board, "exchange": next((b for b in badges if "SME" in b), "Mainboard" if board == "Mainboard" else "Unknown"),
            "status": status, "price": price, "lotSize": lot,
            "gmp": number(bold.text()) if bold else None,
            "gmpPercent": percent(txt("GMP")) if price else None,
            "rating": txt("Rating").count("🔥"), "issueSize": txt("IPO Size") or None,
            "subscription": txt("Sub") or None,
            "openDate": txt("Open").split("GMP:")[0].strip() or None,
            "closeDate": txt("Close").split("GMP:")[0].strip() or None,
            "listingDate": txt("Listing").split("GMP:")[0].strip() or None,
            "sourceUpdated": txt("Updated-On") or None,
            "profitPerLot": None, "estimatedListing": None, "profitSource": "unavailable",
            "detailError": None,
        })
    if not rows:
        raise ValueError("No IPO rows could be read. Keeping the last successful snapshot.")
    return rows


def parse_detail(html):
    doc = Document(html).root
    for table in doc.find("table"):
        for tr in table.find("tr"):
            cells = {td.attrs.get("data-title"): td.text() for td in tr.find("td") if td.attrs.get("data-title")}
            if "GMP" in cells and "Est. Profit" in cells:
                return {
                    "gmp": number(cells["GMP"].split("(")[0]),
                    "gmpPercent": percent(cells["GMP"]),
                    "profitPerLot": number(cells["Est. Profit"]),
                    "estimatedListing": number(cells.get("Est. Listing Price", "")),
                    "sourceUpdated": re.split(r"\s+(?:Sub:|[A-Z](?:\s|$))", cells.get("GMP Date & Time", ""))[0].strip() or None,
                }
    raise ValueError("Latest GMP detail row not found")


def fetch_html(url):
    if urlparse(url).hostname != "www.investorgain.com":
        raise ValueError("Unexpected source host")
    request = Request(url, headers={"User-Agent": "GmpTraqer/1.0 (personal IPO dashboard)", "Accept": "text/html"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=20) as response:
                if urlparse(response.url).hostname != "www.investorgain.com":
                    raise ValueError("Unexpected source redirect")
                return response.read(5_000_000).decode("utf-8", errors="replace")
        except Exception:
            if attempt:
                raise
            time.sleep(1)


def enrich(row, detail):
    row.update(detail)
    row["profitSource"] = "detail" if row["profitPerLot"] is not None else "unavailable"
    if not row["price"]:
        row["gmpPercent"] = row["estimatedListing"] = None
    if not row["lotSize"]:
        row["profitPerLot"] = None
        row["profitSource"] = "unavailable"
    return row


def scrape(fetch=fetch_html, progress=None):
    rows = parse_report(fetch(SOURCE))
    warnings = []
    if progress:
        progress(0, len(rows))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch, row["url"]): row for row in rows}
        for done, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                enrich(row, parse_detail(future.result()))
            except Exception as exc:
                row["detailError"] = str(exc)
                warnings.append(f"{row['name']}: detail unavailable")
                if row["gmp"] is not None and row["lotSize"]:
                    row["profitPerLot"] = round(row["gmp"] * row["lotSize"], 2)
                    row["profitSource"] = "calculated"
                if row["price"] and row["gmp"] is not None:
                    row["estimatedListing"] = round(row["price"] + row["gmp"], 2)
            if progress:
                progress(done, len(rows))
    return {"fetchedAt": datetime.now(timezone.utc).isoformat(), "source": SOURCE, "rows": rows, "warnings": warnings}
