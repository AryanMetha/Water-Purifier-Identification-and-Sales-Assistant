"""
eda_pre.py  —  Pre-embedding data quality audit
================================================
Run BEFORE build_index.py.

Checks:
  1. DB coverage    — products per brand, image availability
  2. Image quality  — resolution, aspect ratio, file size
  3. Duplicates     — identical image files (hash collision)
  4. Visual sample  — saves a contact sheet so you can eyeball quality

Output:
  C:\Misc_progs\RO\ro_v2\eda\eda_pre_report.txt
  C:\Misc_progs\RO\ro_v2\eda\contact_sheet.jpg

Usage:
  python eda_pre.py
"""

import hashlib, json, sqlite3
from collections import defaultdict, Counter
from pathlib import Path
from PIL import Image
import numpy as np

BASE_DIR = Path(r"C:\Misc_progs\RO\ro_v2")
EDA_DIR  = BASE_DIR / "eda"
EDA_DIR.mkdir(exist_ok=True)

DB_PATH  = BASE_DIR / "catalogue_v2.db"
REPORT   = EDA_DIR / "eda_pre_report.txt"

lines = []

def log(s=""):
    print(s)
    lines.append(s)

# ── Load DB ───────────────────────────────────────────────────────────
conn = sqlite3.connect(str(DB_PATH))
rows = conn.execute("""
    SELECT id, source, brand, full_name, category,
           price_inr, local_image, image_url, product_url
    FROM products
""").fetchall()
cols = ["id","source","brand","full_name","category",
        "price_inr","local_image","image_url","product_url"]
products = [dict(zip(cols, r)) for r in rows]
conn.close()

log("=" * 60)
log("  EDA PRE-EMBEDDING REPORT")
log("=" * 60)
log(f"\nTotal products in DB: {len(products)}")

# ── 1. Coverage by brand ──────────────────────────────────────────────
log("\n" + "─" * 60)
log("1. COVERAGE BY BRAND")
log("─" * 60)

by_brand = defaultdict(list)
for p in products:
    by_brand[p["brand"]].append(p)

log(f"\n{'Brand':<20} {'Total':>6} {'Has Image':>10} {'No Image':>9} {'% Coverage':>11}")
log(f"{'─'*20} {'─'*6} {'─'*10} {'─'*9} {'─'*11}")

no_image_products = []
for brand in sorted(by_brand):
    ps       = by_brand[brand]
    has_img  = sum(1 for p in ps if p["local_image"] and Path(p["local_image"]).exists())
    no_img   = len(ps) - has_img
    pct      = has_img / len(ps) * 100
    log(f"{brand:<20} {len(ps):>6} {has_img:>10} {no_img:>9} {pct:>10.0f}%")
    no_image_products.extend([p for p in ps if not p["local_image"]
                               or not Path(p.get("local_image","x")).exists()])

total_img = sum(1 for p in products
                if p["local_image"] and Path(p["local_image"]).exists())
log(f"\n{'TOTAL':<20} {len(products):>6} {total_img:>10} "
    f"{len(products)-total_img:>9} "
    f"{total_img/len(products)*100:>10.0f}%")

if no_image_products:
    log(f"\nProducts WITHOUT local image ({len(no_image_products)}):")
    for p in no_image_products[:20]:
        log(f"  [{p['brand']:<15}] {p['full_name'][:55]}")
    if len(no_image_products) > 20:
        log(f"  ... and {len(no_image_products)-20} more")

# ── 2. Category distribution ──────────────────────────────────────────
log("\n" + "─" * 60)
log("2. CATEGORY DISTRIBUTION")
log("─" * 60)

cats = Counter(p["category"] for p in products)
log("")
for cat, count in cats.most_common():
    bar = "█" * count
    log(f"  {cat:<15} {count:>4}  {bar}")

# ── 3. Image quality audit ────────────────────────────────────────────
log("\n" + "─" * 60)
log("3. IMAGE QUALITY AUDIT")
log("─" * 60)

img_products = [p for p in products
                if p["local_image"] and Path(p["local_image"]).exists()]

widths, heights, sizes, aspects = [], [], [], []
tiny    = []   # < 300px on any side
extreme = []   # aspect ratio > 2:1 or < 1:2
large   = []   # > 1000px (good)

for p in img_products:
    path = Path(p["local_image"])
    try:
        img    = Image.open(path)
        w, h   = img.size
        sz     = path.stat().st_size / 1024  # KB
        aspect = w / h

        widths.append(w)
        heights.append(h)
        sizes.append(sz)
        aspects.append(aspect)

        if w < 300 or h < 300:
            tiny.append((p["brand"], p["full_name"][:45], w, h))
        if aspect > 2.0 or aspect < 0.5:
            extreme.append((p["brand"], p["full_name"][:45], w, h, aspect))
        if w >= 800 and h >= 800:
            large.append(p)
    except Exception as e:
        log(f"  CORRUPT: {path.name}  ({e})")

log(f"\n  Images analysed : {len(img_products)}")
log(f"  High-res (≥800) : {len(large)}  ({len(large)/len(img_products)*100:.0f}%)")
log(f"  Tiny (<300px)   : {len(tiny)}")
log(f"  Extreme ratio   : {len(extreme)}")

if widths:
    log(f"\n  Width  — min:{min(widths)}  median:{int(np.median(widths))}  max:{max(widths)}")
    log(f"  Height — min:{min(heights)}  median:{int(np.median(heights))}  max:{max(heights)}")
    log(f"  Size   — min:{min(sizes):.0f}KB  median:{np.median(sizes):.0f}KB  max:{max(sizes):.0f}KB")
    log(f"  Aspect — min:{min(aspects):.2f}  median:{np.median(aspects):.2f}  max:{max(aspects):.2f}")

if tiny:
    log(f"\n  Tiny images (may hurt embedding quality):")
    for brand, name, w, h in tiny[:10]:
        log(f"    [{brand:<15}] {name}  ({w}x{h})")

if extreme:
    log(f"\n  Extreme aspect ratios (banners/lifestyle shots):")
    for brand, name, w, h, asp in extreme[:10]:
        log(f"    [{brand:<15}] {name}  ({w}x{h}, ratio {asp:.2f})")

# ── 4. Duplicate detection ────────────────────────────────────────────
log("\n" + "─" * 60)
log("4. DUPLICATE IMAGE DETECTION")
log("─" * 60)

hash_map = defaultdict(list)
for p in img_products:
    path = Path(p["local_image"])
    try:
        h = hashlib.md5(path.read_bytes()).hexdigest()
        hash_map[h].append(p)
    except Exception:
        pass

dupes = {h: ps for h, ps in hash_map.items() if len(ps) > 1}
log(f"\n  Unique images   : {len(hash_map) - len(dupes)}")
log(f"  Duplicate groups: {len(dupes)}")
log(f"  Wasted slots    : {sum(len(ps)-1 for ps in dupes.values())}")

if dupes:
    log(f"\n  Duplicate groups (same image file used for multiple products):")
    for h, ps in list(dupes.items())[:8]:
        log(f"  Hash {h[:8]}...  ({len(ps)} products)")
        for p in ps:
            log(f"    [{p['brand']:<15}] {p['full_name'][:50]}")

# ── 5. Price coverage ─────────────────────────────────────────────────
log("\n" + "─" * 60)
log("5. PRICE COVERAGE")
log("─" * 60)

has_price   = [p for p in products if p.get("price_inr")]
no_price    = [p for p in products if not p.get("price_inr")]
prices      = [p["price_inr"] for p in has_price]

log(f"\n  Has price : {len(has_price)} ({len(has_price)/len(products)*100:.0f}%)")
log(f"  No price  : {len(no_price)}")
if prices:
    log(f"  Price range: ₹{int(min(prices)):,} — ₹{int(max(prices)):,}")
    log(f"  Median price: ₹{int(np.median(prices)):,}")

no_price_by_brand = Counter(p["brand"] for p in no_price)
if no_price_by_brand:
    log(f"\n  No-price products by brand:")
    for brand, count in no_price_by_brand.most_common():
        log(f"    {brand:<20} {count}")

# ── 6. Contact sheet ──────────────────────────────────────────────────
log("\n" + "─" * 60)
log("6. GENERATING CONTACT SHEET")
log("─" * 60)

THUMB = 120
COLS  = 12
sample_products = img_products[:COLS * 16]  # up to 16 rows
n     = len(sample_products)
rows  = (n + COLS - 1) // COLS
sheet = Image.new("RGB", (COLS * THUMB, rows * THUMB), (240, 240, 240))

placed = 0
for i, p in enumerate(sample_products):
    try:
        img  = Image.open(p["local_image"]).convert("RGB")
        img.thumbnail((THUMB, THUMB))
        col  = i % COLS
        row  = i // COLS
        # Paste centred in cell
        ox = col * THUMB + (THUMB - img.width)  // 2
        oy = row * THUMB + (THUMB - img.height) // 2
        sheet.paste(img, (ox, oy))
        placed += 1
    except Exception:
        pass

sheet_path = EDA_DIR / "contact_sheet.jpg"
sheet.save(str(sheet_path), "JPEG", quality=88)
log(f"\n  Contact sheet saved: {sheet_path}")
log(f"  ({placed} products, {THUMB}px thumbnails)")

# ── Summary + recommendations ─────────────────────────────────────────
log("\n" + "=" * 60)
log("SUMMARY & RECOMMENDATIONS")
log("=" * 60)

img_pct = total_img / len(products) * 100
log(f"\n  DB size       : {len(products)} products")
log(f"  Image coverage: {img_pct:.0f}%  ({total_img} with image)")
log(f"  Duplicates    : {len(dupes)} groups")
log(f"  Tiny images   : {len(tiny)}")
log(f"  Price coverage: {len(has_price)/len(products)*100:.0f}%")

log("\n  Recommendations:")
if img_pct < 80:
    log(f"  ⚠ Image coverage {img_pct:.0f}% is low — re-scrape missing images")
else:
    log(f"  ✓ Image coverage {img_pct:.0f}% is good")

if len(tiny) > 5:
    log(f"  ⚠ {len(tiny)} tiny images — consider re-downloading at higher res")
else:
    log(f"  ✓ Very few tiny images")

if len(dupes) > 10:
    log(f"  ⚠ {len(dupes)} duplicate image groups — variants may confuse search")
else:
    log(f"  ✓ Few duplicates")

underrep = [(b, len(ps)) for b, ps in by_brand.items() if len(ps) < 5]
if underrep:
    log(f"  ⚠ Underrepresented brands (<5 products):")
    for b, c in sorted(underrep, key=lambda x: x[1]):
        log(f"      {b}: {c} products")

log(f"\n  Report saved: {REPORT}")

REPORT.write_text("\n".join(lines), encoding="utf-8")