"""
Chiswick Auctions — Lot Detail scraper (second pass)

Visits individual lot pages (saved in chiswick_rugs.db by scraper.py) and
pulls the fuller detail: description text, condition rating, image URL,
provenance/notes if present.

Respects robots.txt: crawl-delay: 10 (10 seconds between requests).

IMPORTANT: I built the HTML parsing here from general knowledge of how these
auction-platform lot pages tend to be structured (Bidpath, which powers
Chiswick's site, per the "Empowered by Bidpath" footer), not from a live
sample of an actual lot page — I didn't have a way to fetch one directly.
The selectors below use safe fallbacks (meta tags, keyword-anchored search)
so they *should* degrade gracefully rather than crash, but the OUTPUT
QUALITY may need tuning. After your first run, if description/condition
fields come back mostly empty, paste me a snippet of what --debug prints
and I'll adjust the parsing.

Usage:
    python lot_details.py                # process all lots not yet detailed
    python lot_details.py --limit 20     # just the first 20 (good for testing)
    python lot_details.py --deals-only   # only lots analyze.py flagged as deals
    python lot_details.py --debug        # print raw extracted text per lot for troubleshooting
"""

import re
import sys
import time
import sqlite3
import argparse
import requests
from bs4 import BeautifulSoup

BASE = "https://www.chiswickauctions.co.uk"
CRAWL_DELAY_SECONDS = 10  # per robots.txt

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RugCompsResearchBot/1.0; +mailto:youremail@example.com)"
}

DB_PATH = "chiswick_rugs.db"


def init_detail_columns(conn):
    cur = conn.cursor()
    # Add detail columns to the existing lots table if they aren't there yet.
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(lots)").fetchall()}
    new_cols = {
        "description": "TEXT",
        "condition_rating": "TEXT",
        "image_url": "TEXT",
        "provenance": "TEXT",
        "details_fetched": "INTEGER DEFAULT 0",
    }
    for col, coltype in new_cols.items():
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE lots ADD COLUMN {col} {coltype}")
    conn.commit()


def fetch_lot_page(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_lot_detail(html, debug=False):
    soup = BeautifulSoup(html, "html.parser")
    result = {"description": None, "condition_rating": None, "image_url": None, "provenance": None}

    # --- Image: og:image meta tag is the most reliable cross-site bet ---
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        result["image_url"] = og_image["content"]

    # --- Description: try og:description first, then meta description,
    #     then fall back to searching for a content block ---
    og_desc = soup.find("meta", property="og:description")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if og_desc and og_desc.get("content"):
        result["description"] = og_desc["content"].strip()
    elif meta_desc and meta_desc.get("content"):
        result["description"] = meta_desc["content"].strip()
    else:
        # Fallback: look for a div/section whose class hints at lot details
        candidate = soup.find(["div", "section"], class_=re.compile(r"lot.?(desc|detail|info)", re.I))
        if candidate:
            result["description"] = candidate.get_text(" ", strip=True)

    full_text = soup.get_text(" ", strip=True)

    # --- Condition rating: e.g. "Condition rating A/B" ---
    m = re.search(r"[Cc]ondition\s*[Rr]ating[:\s]*([A-D](?:\s*/\s*[A-D])?)", full_text)
    if m:
        result["condition_rating"] = m.group(1).replace(" ", "")

    # --- Provenance: grab text following the word "Provenance" up to the next likely field ---
    m = re.search(r"Provenance[:\s]+(.{10,300}?)(?:\.\s[A-Z]|Condition|Estimate|$)", full_text)
    if m:
        result["provenance"] = m.group(1).strip()

    if debug:
        print("----- DEBUG: extracted fields -----")
        print(result)
        print("----- DEBUG: first 500 chars of page text -----")
        print(full_text[:500])
        print("------------------------------------")

    return result


def get_target_lots(conn, limit=None, deals_only=False):
    cur = conn.cursor()
    query = "SELECT lot_url FROM lots WHERE (details_fetched IS NULL OR details_fetched = 0)"
    if deals_only:
        # Matches analyze.py's rough deal heuristic: unsold lots with an estimate.
        query += " AND is_sold = 0 AND estimate_high_gbp IS NOT NULL"
    query += " ORDER BY lot_url"
    if limit:
        query += f" LIMIT {int(limit)}"
    return [row[0] for row in cur.execute(query).fetchall()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Max number of lots to process")
    parser.add_argument("--deals-only", action="store_true", help="Only process unsold lots with estimates")
    parser.add_argument("--debug", action="store_true", help="Print raw extracted text per lot")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_detail_columns(conn)

    targets = get_target_lots(conn, limit=args.limit, deals_only=args.deals_only)
    if not targets:
        print("Nothing to fetch — either the DB is empty, or all lots already have details.")
        print("(Run scraper.py first if the DB is empty.)")
        return

    print(f"Fetching details for {len(targets)} lot(s). This will take roughly "
          f"{len(targets) * CRAWL_DELAY_SECONDS / 60:.1f} minutes due to the crawl delay.\n")

    cur = conn.cursor()
    for i, url in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {url}")
        try:
            html = fetch_lot_page(url)
            details = parse_lot_detail(html, debug=args.debug)
            cur.execute("""
                UPDATE lots
                SET description = ?, condition_rating = ?, image_url = ?,
                    provenance = ?, details_fetched = 1
                WHERE lot_url = ?
            """, (details["description"], details["condition_rating"],
                  details["image_url"], details["provenance"], url))
            conn.commit()
        except requests.RequestException as e:
            print(f"  ! Failed to fetch: {e}")

        if i < len(targets):
            time.sleep(CRAWL_DELAY_SECONDS)

    print("\nDone.")
    conn.close()


if __name__ == "__main__":
    main()
