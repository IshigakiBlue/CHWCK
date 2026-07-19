"""
Compute a CLIP embedding (a vector representing visual pattern/style/color)
for each downloaded carpet image, and store it in the database.

No crawl-delay needed here — this runs entirely locally on your machine,
no requests to Chiswick's site.

First run downloads the CLIP model itself (~600MB), which is separate from
the ~1-2GB PyTorch install. Both are one-time.

Usage:
    pip install torch transformers pillow --break-system-packages   # if not already
    python embed_images.py
    python embed_images.py --limit 20   # test on a small batch first
"""

import sqlite3
import argparse
import numpy as np
from PIL import Image

DB_PATH = "chiswick_rugs.db"
MODEL_NAME = "openai/clip-vit-base-patch32"  # 512-dim embeddings, good balance of speed/quality


def init_column(conn):
    cur = conn.cursor()
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(lots)").fetchall()}
    if "embedding" not in existing_cols:
        cur.execute("ALTER TABLE lots ADD COLUMN embedding BLOB")
    conn.commit()


def load_model():
    # Imported here so the rest of the script's --help works even before torch is installed.
    import torch
    from transformers import CLIPModel, CLIPProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading {MODEL_NAME} on {device} (first run downloads the model, ~600MB)...")
    model = CLIPModel.from_pretrained(MODEL_NAME).to(device)
    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    model.eval()
    return model, processor, device


def embed_image(model, processor, device, image_path):
    import torch

    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        features = model.get_image_features(**inputs)
    # Normalize so cosine similarity is just a dot product later
    features = features / features.norm(p=2, dim=-1, keepdim=True)
    return features.cpu().numpy().astype(np.float32).flatten()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_column(conn)
    cur = conn.cursor()

    query = """
        SELECT lot_url, local_image_path FROM lots
        WHERE local_image_path IS NOT NULL
          AND embedding IS NULL
    """
    if args.limit:
        query += f" LIMIT {int(args.limit)}"

    targets = cur.execute(query).fetchall()

    if not targets:
        print("Nothing to embed — either no local images yet (run download_images.py first), "
              "or everything's already embedded.")
        return

    model, processor, device = load_model()

    print(f"\nEmbedding {len(targets)} image(s)...\n")
    for i, (lot_url, image_path) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {image_path}")
        try:
            vec = embed_image(model, processor, device, image_path)
            cur.execute("UPDATE lots SET embedding = ? WHERE lot_url = ?", (vec.tobytes(), lot_url))
            conn.commit()
        except Exception as e:
            print(f"  ! Failed: {e}")

    print("\nDone.")
    conn.close()


if __name__ == "__main__":
    main()
