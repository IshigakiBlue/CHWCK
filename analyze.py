"""
Analyze chiswick_rugs.db:
1. Extract a rough "type" (e.g. Tabriz, Kashan, Heriz, Kilim...) from each title.
2. Compute median/average sold price per type from SOLD lots (your comps).
3. Compare currently-active (unsold, has estimate) lots against those comps
   and flag ones whose HIGH estimate sits well below the median sold comp —
   i.e. plausible deals if they hammer near estimate.

Run scraper.py first to populate the database.
"""

import re
import sqlite3
import statistics

DB_PATH = "chiswick_rugs.db"

# Common rug/carpet origin & type keywords seen in Chiswick titles.
# Extend this list as you see more patterns in your scraped data.
TYPE_KEYWORDS = [
    "tabriz", "kashan", "heriz", "isfahan", "qum", "nain", "sarouk", "mahal",
    "malayer", "bakhtiar", "hamadan", "kerman", "khorassan", "senneh",
    "qashqai", "afshar", "bijar", "kazak", "shirvan", "karabagh", "moghan",
    "kilim", "kelim", "suzani", "bokhara", "yomut", "tekke", "ersari",
    "konya", "ushak", "hereke", "dagestan", "belouch", "baluch",
]


def extract_type(title):
    t = title.lower()
    for kw in TYPE_KEYWORDS:
        if kw in t:
            return kw.title()
    return "Other/Unclassified"


def extract_size_m2(title):
    """Look for patterns like '3.28m x 2.23m' and return area in m^2."""
    m = re.search(r"(\d+[.,]\d+)\s*m\s*x\s*(\d+[.,]\d+)", title.lower())
    if m:
        a = float(m.group(1).replace(",", "."))
        b = float(m.group(2).replace(",", "."))
        return round(a * b, 2)
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    rows = cur.execute("SELECT lot_url, title, sold_price_gbp, estimate_low_gbp, estimate_high_gbp, is_sold FROM lots").fetchall()
    if not rows:
        print("No data yet — run scraper.py first.")
        return

    sold_by_type = {}
    active_lots = []

    for lot_url, title, sold_price, est_low, est_high, is_sold in rows:
        rug_type = extract_type(title)
        size_m2 = extract_size_m2(title)

        if is_sold and sold_price:
            sold_by_type.setdefault(rug_type, []).append({
                "price": sold_price, "size_m2": size_m2, "title": title, "url": lot_url
            })
        elif not is_sold and est_high:
            active_lots.append({
                "type": rug_type, "title": title, "url": lot_url,
                "est_low": est_low, "est_high": est_high, "size_m2": size_m2
            })

    print("=== Sold comps by type (median price) ===")
    comps = {}
    for rug_type, entries in sorted(sold_by_type.items(), key=lambda x: -len(x[1])):
        prices = [e["price"] for e in entries]
        median_price = statistics.median(prices)
        comps[rug_type] = median_price
        print(f"{rug_type:20s} n={len(prices):3d}  median £{median_price:,.0f}  "
              f"(range £{min(prices):,.0f}–£{max(prices):,.0f})")

    print("\n=== Active lots that look like potential deals ===")
    print("(high estimate is notably below the median sold price for that type)\n")

    DEAL_THRESHOLD = 0.6  # flag if high estimate < 60% of median comp

    found_any = False
    for lot in sorted(active_lots, key=lambda l: l["est_high"]):
        comp_median = comps.get(lot["type"])
        if comp_median and lot["est_high"] < comp_median * DEAL_THRESHOLD:
            found_any = True
            print(f"[{lot['type']}] {lot['title']}")
            print(f"  Estimate: £{lot['est_low']:.0f}-£{lot['est_high']:.0f}  "
                  f"vs. comp median £{comp_median:,.0f}")
            print(f"  {lot['url']}\n")

    if not found_any:
        print("None found with current threshold — try lowering DEAL_THRESHOLD "
              "or scraping more search terms for better comp coverage.")

    conn.close()


if __name__ == "__main__":
    main()
