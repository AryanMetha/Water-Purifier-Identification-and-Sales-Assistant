"""
build_index.py
==============
Encodes all catalogue images with CLIP and saves the index.

Output files (same folder as script / DB):
  C:\Misc_progs\RO\ro_v2\clip_vectors.npy      float32 array [N, 512]
  C:\Misc_progs\RO\ro_v2\clip_index.json        [{id, product_id, local_image, full_name, brand, ...}]

Usage:
  python build_index.py              # encode everything with images
  python build_index.py --rebuild    # force re-encode even if index exists
"""

import argparse, json, sqlite3, time
import numpy as np
from pathlib import Path
from PIL import Image

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR    = Path(r"C:\Misc_progs\RO\ro_v2")
DB_PATH     = BASE_DIR / "catalogue_v2.db"
VECTORS_OUT = BASE_DIR / "clip_vectors.npy"
INDEX_OUT   = BASE_DIR / "clip_index.json"

# ── Load CLIP ─────────────────────────────────────────────────────────
def load_clip():
    """
    Load CLIP via HuggingFace transformers.
    Uses openai/clip-vit-base-patch32 — 151MB download on first run.
    """
    print("Loading CLIP model (openai/clip-vit-base-patch32)...")
    from transformers import CLIPProcessor, CLIPModel
    import torch
    model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    device    = "cuda" if torch.cuda.is_available() else "cpu"
    model     = model.to(device)
    model.eval()
    print(f"  Device: {device}")
    return model, processor, device

def encode_image(model, processor, device, img_path):
    import torch
    import torch.nn.functional as F
    try:
        img    = Image.open(img_path).convert("RGB")
        inputs = processor(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            # Use vision_model directly - always returns a tensor via pooler_output
            vision_out = model.vision_model(**inputs)
            feats = vision_out.pooler_output          # [1, 768] or [1, 512]
            feats = model.visual_projection(feats)    # -> [1, 512]
            feats = F.normalize(feats, dim=-1)
        return feats.cpu().numpy().astype(np.float32).squeeze()
    except Exception as e:
        print(f"    WARN: encode failed for {img_path}: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────
def build_index(rebuild=False):
    if VECTORS_OUT.exists() and INDEX_OUT.exists() and not rebuild:
        print(f"Index already exists ({VECTORS_OUT})")
        print("Run with --rebuild to force re-encode.")
        existing = json.loads(INDEX_OUT.read_text())
        print(f"Current index: {len(existing)} products")
        return

    # Load products from DB
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT id, source, brand, model, full_name, category,
               price_inr, mrp_inr, discount_pct, rating, review_count,
               availability, image_url, local_image, product_url
        FROM products
        WHERE local_image != '' AND local_image IS NOT NULL
    """).fetchall()
    cols = ["id","source","brand","model","full_name","category",
            "price_inr","mrp_inr","discount_pct","rating","review_count",
            "availability","image_url","local_image","product_url"]
    products = [dict(zip(cols, r)) for r in rows]
    conn.close()

    print(f"\nProducts with images: {len(products)}")

    # Load CLIP
    model, processor, device = load_clip()

    # Encode
    vectors  = []
    index    = []
    failed   = 0
    t0       = time.time()

    for i, p in enumerate(products):
        img_path = Path(p["local_image"])
        if not img_path.exists():
            print(f"  [{i+1}/{len(products)}] MISSING: {img_path.name}")
            failed += 1
            continue

        vec = encode_image(model, processor, device, img_path)
        if vec is None:
            failed += 1
            continue

        vectors.append(vec)
        index.append({
            "vec_idx":      len(vectors) - 1,
            "id":           p["id"],
            "source":       p["source"],
            "brand":        p["brand"],
            "model":        p["model"],
            "full_name":    p["full_name"],
            "category":     p["category"],
            "price_inr":    p["price_inr"],
            "mrp_inr":      p["mrp_inr"],
            "discount_pct": p["discount_pct"],
            "availability": p["availability"],
            "image_url":    p["image_url"],
            "local_image":  p["local_image"],
            "product_url":  p["product_url"],
        })

        if (i + 1) % 10 == 0 or (i + 1) == len(products):
            elapsed = time.time() - t0
            rate    = (i + 1) / elapsed
            print(f"  [{i+1}/{len(products)}] {p['brand']:<15} {p['full_name'][:40]}"
                  f"  ({rate:.1f}/s)")

    # Save
    vectors_arr = np.stack(vectors).astype(np.float32)  # [N, 512]
    np.save(str(VECTORS_OUT), vectors_arr)
    INDEX_OUT.write_text(json.dumps(index, indent=2, ensure_ascii=False))

    elapsed = time.time() - t0
    print(f"\n{'='*50}")
    print(f"  Encoded  : {len(vectors)} products")
    print(f"  Failed   : {failed}")
    print(f"  Shape    : {vectors_arr.shape}")
    print(f"  Time     : {elapsed:.1f}s")
    print(f"  Saved to : {VECTORS_OUT}")
    print(f"             {INDEX_OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-encode even if index already exists")
    args = parser.parse_args()
    build_index(rebuild=args.rebuild)