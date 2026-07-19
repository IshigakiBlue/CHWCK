"""
Download the actual image files referenced by lots.image_url (populated by
lot_details.py) so we have local files to feed into the CLIP embedding step.

Respects the 10-second crawl delay, same as the other scripts, since these
images are hosted on Chiswick's own domain.

Usage:
    python download_images.py
    python download_images.py --limit 20
"""

import os
import re
import time
import sqlite3
import argparse
import requests

DB_PATH = "chiswick_rugs.db"
IMAGES_DIR = "images"
CRAWL_DELAY_SECONDS = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RugCompsResearchBot/1.0; +mailto:youremail@example.com)"
}


def init_column(conn):
    cur = conn.cursor()
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(lots)").fetchall()}
    if "local_image_path" not in existing_cols:
        cur.execute("ALTER TABLE lots ADD COLUMN local_image_path TEXT")
    conn.commit()


def safe_filename(lot_url):
    """Turn a lot URL into a filesystem-safe filename."""
    name = re.sub(r"^https?://", "", lot_url)
    name = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")
    return name[:150] + ".jpg"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    os.makedirs(IMAGES_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    init_column(conn)
    cur = conn.cursor()

    query = """
        SELECT lot_url, image_url FROM lots
        WHERE image_url IS NOT NULL
          AND (local_image_path IS NULL OR local_image_path = '')
    """
    if args.limit:
        query += f" LIMIT {int(args.limit)}"

    targets = cur.execute(query).fetchall()

    if not targets:
        print("Nothing to download — either no image_urls yet (run lot_details.py first), "
              "or everything's already downloaded.")
        return

    print(f"Downloading {len(targets)} image(s). This will take roughly "
          f"{len(targets) * CRAWL_DELAY_SECONDS / 60:.1f} minutes.\n")

    for i, (lot_url, image_url) in enumerate(targets, 1):
        filename = safe_filename(lot_url)
        filepath = os.path.join(IMAGES_DIR, filename)
        print(f"[{i}/{len(targets)}] {image_url}")

        try:
            resp = requests.get(image_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)
            cur.execute("UPDATE lots SET local_image_path = ? WHERE lot_url = ?", (filepath, lot_url))
            conn.commit()
        except requests.RequestException as e:
            print(f"  ! Failed: {e}")

        if i < len(targets):
            time.sleep(CRAWL_DELAY_SECONDS)

    print("\nDone.")
    conn.close()


if __name__ == "__main__":
    main()
