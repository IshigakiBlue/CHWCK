"""
Chiswick Auctions — Rugs & Carpets scraper

Pulls past (sold) and current lot listings for rugs/carpets from
chiswickauctions.co.uk's public search, and stores them in SQLite.

Respects robots.txt: crawl-delay: 10 (10 seconds between requests).
No login-gated or /account/ pages are touched.

Usage:
    pip install requests beautifulsoup4
    python scraper.py
"""

import re
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://www.chiswickauctions.co.uk"
SEARCH_URL = f"{BASE}/auction/search/"
CRAWL_DELAY_SECONDS = 10  # per robots.txt

HEADERS = {
    # Identify yourself honestly. Swap in your own contact info.
    "User-Agent": "Mozilla/5.0 (compatible; RugCompsResearchBot/1.0; +mailto:youremail@example.com)"
}

# Search keywords to sweep — Chiswick's search box matches free text against
# lot titles/descriptions. We run several passes and de-dupe by lot URL,
# since a single "carpet" query won't catch every synonym (rug, kilim, etc).
SEARCH_TERMS = ["carpet", "rug", "kilim", "kelim", "suzani", "kazak", "tabriz"]

DB_PATH = "chiswick_rugs.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lots (
            lot_url TEXT PRIMARY KEY,
            title TEXT,
            sold_price_gbp REAL,
            estimate_low_gbp REAL,
            estimate_high_gbp REAL,
            is_sold INTEGER,
            search_term TEXT,
            scraped_at TEXT
        )
    """)
    conn.commit()
    return conn


def parse_price(text):
    """'Sold for £280' -> 280.0"""
    m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def parse_estimate(text):
    """'Estimated at £150 - £200' -> (150.0, 200.0)"""
    m = re.search(r"£\s*([\d,]+).*?£\s*([\d,]+)", text)
    if m:
        return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
    return None, None


def fetch_page(search_term, page_num, per_page=96):
    params = {
        "so": 0,          # sort order
        "st": search_term,
        "sto": 0,         # "all words any order"
        "au": "",         # all auctions
        "ef": "",
        "et": "",
        "ic": "False",
        "sd": 1,
        "pp": per_page,
        "pn": page_num,
        "g": 1,           # grid/list flag — harmless either way
    }
    resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_search_results(html):
    """
    Returns a list of dicts, one per lot card found on the page.
    Also returns the total page count so the caller knows when to stop.
    """
    soup = BeautifulSoup(html, "html.parser")
    lots = []

    # Each lot card has a link to /auction/lot/... with the lot title as text,
    # followed by a "Sold for £X" or "Estimated at £X - £Y" line.
    lot_links = soup.select('a[href*="/auction/lot/"]')

    seen_urls = set()
    for link in lot_links:
        href = link.get("href")
        if not href or href in seen_urls:
            continue
        title = link.get_text(strip=True)
        if not title or title.startswith("http"):
            continue  # skip the image-wrapper <a> tags with no text
        seen_urls.add(href)

        # Walk forward through siblings to find the price line
        # (structure: title link -> ... -> "Sold for £X" / "Estimated at ...")
        price_text = ""
        node = link.find_parent()
        if node:
            container_text = node.get_text(" ", strip=True)
            m = re.search(r"(Sold for £[\d,]+|Estimated at £[\d,]+\s*-\s*£[\d,]+)", container_text)
            if m:
                price_text = m.group(1)

        is_sold = price_text.startswith("Sold")
        sold_price = parse_price(price_text) if is_sold else None
        est_low, est_high = parse_estimate(price_text) if not is_sold else (None, None)

        lots.append({
            "lot_url": urljoin(BASE, href),
            "title": title,
            "sold_price_gbp": sold_price,
            "estimate_low_gbp": est_low,
            "estimate_high_gbp": est_high,
            "is_sold": int(is_sold),
        })

    # Detect total page count from pagination text like "of 11"
    total_pages = 1
    page_text = soup.get_text()
    m = re.search(r"of\s+(\d+)\s*$", page_text.strip().split("\n")[-1]) or re.search(r"\bof\s+(\d+)\b", page_text)
    if m:
        total_pages = int(m.group(1))

    return lots, total_pages


def scrape_all():
    conn = init_db()
    cur = conn.cursor()
    total_new = 0

    for term in SEARCH_TERMS:
        print(f"\n=== Searching for '{term}' ===")
        page = 1
        total_pages = 1

        while page <= total_pages:
            print(f"  Fetching page {page}/{total_pages}...")
            html = fetch_page(term, page)
            lots, detected_total_pages = parse_search_results(html)

            if page == 1:
                total_pages = detected_total_pages
                print(f"  ({total_pages} total pages for this term)")

            for lot in lots:
                cur.execute("""
                    INSERT INTO lots (lot_url, title, sold_price_gbp, estimate_low_gbp,
                                       estimate_high_gbp, is_sold, search_term, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(lot_url) DO NOTHING
                """, (lot["lot_url"], lot["title"], lot["sold_price_gbp"],
                      lot["estimate_low_gbp"], lot["estimate_high_gbp"],
                      lot["is_sold"], term))
                if cur.rowcount:
                    total_new += 1

            conn.commit()
            page += 1

            if page <= total_pages:
                time.sleep(CRAWL_DELAY_SECONDS)  # respect robots.txt crawl-delay

        time.sleep(CRAWL_DELAY_SECONDS)  # delay between search terms too

    print(f"\nDone. {total_new} new lots saved to {DB_PATH}.")
    conn.close()


if __name__ == "__main__":
    scrape_all()
