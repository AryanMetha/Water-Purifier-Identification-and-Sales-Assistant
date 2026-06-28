"""
search.py - RO Catalogue Image Search
Usage:
  python search.py path/to/image.jpg
  python search.py path/to/image.jpg --top 10
  python search.py path/to/image.jpg --no-tta
  python search.py --test
"""

import argparse, json, time
import numpy as np
from pathlib import Path
from PIL import Image, ImageEnhance

BASE_DIR     = Path(r"C:\Misc_progs\RO\ro_v2")
VECTORS_PATH = BASE_DIR / "clip_vectors.npy"
INDEX_PATH   = BASE_DIR / "clip_index.json"

TEST_IMAGES = [
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\5e9e88fb1a18.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\4e490a5df677.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\ef0c47d18e17.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\fb888694eab5.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\b84050da12fd.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\1e29797e22b3.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\3c57744eb37e.jpg",
]

def load_index():
    if not VECTORS_PATH.exists() or not INDEX_PATH.exists():
        raise FileNotFoundError(f"Index not found. Run build_index.py first.")
    vectors = np.load(str(VECTORS_PATH))
    index   = json.loads(INDEX_PATH.read_text())
    assert len(vectors) == len(index), "Index size mismatch - run build_index.py --rebuild"
    return vectors, index

_clip_cache = {}

def get_clip():
    if _clip_cache:
        return _clip_cache["model"], _clip_cache["processor"], _clip_cache["device"]
    import torch
    from transformers import CLIPProcessor, CLIPModel
    print("Loading CLIP model...")
    model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    device    = "cuda" if torch.cuda.is_available() else "cpu"
    model     = model.to(device).eval()
    print(f"  Device: {device}")
    _clip_cache.update({"model": model, "processor": processor, "device": device})
    return model, processor, device

def encode_single(img):
    import torch
    import torch.nn.functional as F
    model, processor, device = get_clip()
    inputs = processor(images=img, return_tensors="pt").to(device)
    with torch.no_grad():
        vision_out = model.vision_model(pixel_values=inputs["pixel_values"])
        feats      = vision_out.pooler_output
        feats      = model.visual_projection(feats)
        feats      = F.normalize(feats, dim=-1)
    return feats.detach().cpu().numpy().astype("float32").squeeze()

def augmented_query_vector(img):
    w, h  = img.size
    side  = min(w, h)
    base  = img.crop(((w-side)//2, (h-side)//2,
                      (w+side)//2, (h+side)//2)).resize((224, 224))
    augments = [
        base,
        base.rotate(10,  resample=Image.BILINEAR),
        base.rotate(-10, resample=Image.BILINEAR),
        ImageEnhance.Brightness(base).enhance(1.2),
        ImageEnhance.Brightness(base).enhance(0.8),
        ImageEnhance.Contrast(base).enhance(1.3),
        base.transpose(Image.FLIP_LEFT_RIGHT),
        base.crop((11, 11, 213, 213)).resize((224, 224)),
    ]
    vecs = np.stack([encode_single(a) for a in augments])
    avg  = vecs.mean(axis=0)
    avg  = avg / np.linalg.norm(avg)
    return avg.astype("float32")

def search(query_image_path, top_k=5, use_tta=True):
    t0             = time.time()
    vectors, index = load_index()
    img            = Image.open(query_image_path).convert("RGB")
    q_vec          = augmented_query_vector(img) if use_tta else encode_single(img)
    scores         = vectors @ q_vec
    top_idxs       = np.argsort(scores)[::-1][:top_k]
    results = []
    for rank, idx in enumerate(top_idxs, 1):
        entry          = index[int(idx)].copy()
        entry["rank"]  = rank
        entry["score"] = float(scores[idx])
        results.append(entry)
    print(f"  Search: {(time.time()-t0)*1000:.0f}ms  ({'TTA' if use_tta else 'no-TTA'})")
    return results

def print_results(results, query_path=""):
    if query_path:
        print(f"\nQuery: {query_path}")
    print("-" * 72)
    print(f"{'#':<3} {'Score':<7} {'Brand':<16} {'Name':<36} {'Price':>8}")
    print("-" * 72)
    for r in results:
        price = f"Rs.{int(r['price_inr']):,}" if r.get("price_inr") else "?"
        print(f"{r['rank']:<3} {r['score']:.4f}  "
              f"{r['brand']:<16} {r['full_name'][:35]:<36} {price:>8}")
    print("-" * 72)
    top = results[0]
    print(f"\nTop match:")
    print(f"  Name    : {top['full_name']}")
    print(f"  Brand   : {top['brand']}")
    print(f"  Category: {top['category']}")
    if top.get("price_inr"):
        mrp  = f"  MRP Rs.{int(top['mrp_inr']):,}" if top.get("mrp_inr") else ""
        disc = f"  {top['discount_pct']}% off"      if top.get("discount_pct") else ""
        print(f"  Price   : Rs.{int(top['price_inr']):,}{mrp}{disc}")
    print(f"  URL     : {top.get('product_url','')}")
    print(f"  Image   : {top.get('local_image','')}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image",    nargs="?")
    parser.add_argument("--top",    type=int, default=5)
    parser.add_argument("--no-tta", action="store_true")
    parser.add_argument("--test",   action="store_true")
    args    = parser.parse_args()
    use_tta = not args.no_tta

    if args.test:
        get_clip()
        print(f"Running {len(TEST_IMAGES)} test images\n")
        for img_path in TEST_IMAGES:
            if not Path(img_path).exists():
                print(f"MISSING: {img_path}")
                continue
            try:
                print_results(search(img_path, top_k=args.top, use_tta=use_tta), img_path)
                print()
            except Exception as e:
                import traceback; traceback.print_exc()
    elif args.image:
        if not Path(args.image).exists():
            print(f"File not found: {args.image}"); exit(1)
        get_clip()
        print_results(search(args.image, top_k=args.top, use_tta=use_tta), args.image)
    else:
        parser.print_help()