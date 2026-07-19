"""
For every active (unsold) lot with an embedding, find the most visually
similar SOLD lots (your comps) using cosine similarity between CLIP
embeddings, and produce a combined confidence score that blends:

  - visual similarity (from CLIP embeddings)
  - text-based type match (from analyze.py's keyword extraction)

This gives you a much better-grounded "is this a good comp?" signal than
keyword-matching alone, since two carpets can share a keyword but look
totally different (or vice versa — an untitled/misclassified rug that
still looks just like a Tabriz).

Usage:
    python visual_match.py
    python visual_match.py --top-k 3          # show top 3 matches per lot instead of 5
    python visual_match.py --lot-url <url>    # just check one specific lot
"""

import sqlite3
import argparse
import numpy as np

from analyze import extract_type

DB_PATH = "chiswick_rugs.db"


def load_embeddings(conn, is_sold):
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT lot_url, title, embedding, sold_price_gbp, estimate_low_gbp, estimate_high_gbp
        FROM lots
        WHERE embedding IS NOT NULL AND is_sold = ?
    """, (1 if is_sold else 0,)).fetchall()

    result = []
    for lot_url, title, emb_blob, sold_price, est_low, est_high in rows:
        vec = np.frombuffer(emb_blob, dtype=np.float32)
        result.append({
            "lot_url": lot_url, "title": title, "vec": vec,
            "sold_price": sold_price, "est_low": est_low, "est_high": est_high,
            "type": extract_type(title or ""),
        })
    return result


def cosine_sim(a, b):
    # Both vectors are already L2-normalized from embed_images.py, so this is just a dot product.
    return float(np.dot(a, b))


def combined_confidence(visual_sim, type_match):
    """
    Blend visual similarity (0-1) with a boolean type match.
    Weighted toward visual similarity since it's the more informative signal,
    but a type-keyword match gives a meaningful boost — think of it as
    corroborating evidence rather than the primary signal.
    """
    base = visual_sim
    if type_match:
        base = min(1.0, base + 0.10)
    return base


def find_matches(active_lot, sold_lots, top_k):
    scored = []
    for sold in sold_lots:
        sim = cosine_sim(active_lot["vec"], sold["vec"])
        type_match = (active_lot["type"] == sold["type"]) and (active_lot["type"] != "Other/Unclassified")
        conf = combined_confidence(sim, type_match)
        scored.append({**sold, "visual_sim": sim, "type_match": type_match, "confidence": conf})

    scored.sort(key=lambda x: -x["confidence"])
    return scored[:top_k]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--lot-url", default=None, help="Only check this one active lot")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    active_lots = load_embeddings(conn, is_sold=False)
    sold_lots = load_embeddings(conn, is_sold=True)

    if not active_lots:
        print("No embedded active lots found. Run download_images.py then embed_images.py first.")
        return
    if not sold_lots:
        print("No embedded sold lots found (no comps to match against). "
              "Run download_images.py then embed_images.py first.")
        return

    if args.lot_url:
        active_lots = [l for l in active_lots if l["lot_url"] == args.lot_url]
        if not active_lots:
            print("That lot_url wasn't found among embedded active lots.")
            return

    for lot in active_lots:
        print(f"\n=== {lot['title']} ===")
        print(f"    {lot['lot_url']}")
        if lot["est_low"] and lot["est_high"]:
            print(f"    Estimate: £{lot['est_low']:.0f}-£{lot['est_high']:.0f}")

        matches = find_matches(lot, sold_lots, args.top_k)
        for m in matches:
            tag = "type+visual" if m["type_match"] else "visual only"
            print(f"    [{m['confidence']:.2f} conf, {tag}] £{m['sold_price']:.0f}  {m['title']}")
            print(f"        {m['lot_url']}")

    conn.close()


if __name__ == "__main__":
    main()
