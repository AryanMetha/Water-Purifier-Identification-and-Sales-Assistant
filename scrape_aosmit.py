"""
scrape_aosmith.py - AO Smith India scraper
==========================================
Uses WordPress REST API /wp-json/wp/v2/product (no auth needed, 95 products).
Falls back to product page HTML for price + image if not in API response.

Run standalone:
    python scrape_aosmith.py
"""

import re, json, time, random, hashlib, sqlite3, logging
import io, sys, requests, traceback
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image

BASE_DIR  = Path(r"C:\Misc_progs\RO\ro_v2")
IMAGE_DIR = BASE_DIR / "images"
DB_PATH   = BASE_DIR / "catalogue_v2.db"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

def get_log():
    logger = logging.getLogger("ro_v2")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        fmt  = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        utf8 = (io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                errors="replace", line_buffering=True)
                if hasattr(sys.stdout, "buffer") else sys.stdout)
        ch = logging.StreamHandler(utf8)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    return logger
log = get_log()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"

def hdrs(referer="https://www.aosmithindia.com/"):
    return {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
            "Referer": referer}

@dataclass
class Product:
    id:           str = ""
    source:       str = ""
    brand:        str = ""
    model:        str = ""
    full_name:    str = ""
    category:     str = ""
    storage_l:    Optional[float] = None
    capacity_lph: Optional[float] = None
    price_inr:    Optional[float] = None
    mrp_inr:      Optional[float] = None
    discount_pct: Optional[float] = None
    rating:       Optional[float] = None
    review_count: Optional[int]   = None
    availability: str = "unknown"
    image_url:    str = ""
    local_image:  str = ""
    product_url:  str = ""
    scraped_at:   str = field(default_factory=lambda: datetime.now().isoformat())

    def make_id(self):
        self.id = hashlib.md5(
            f"{self.source}{self.product_url}".encode()).hexdigest()[:12]
        return self

CAT_PATTERNS = [
    (r"ro\s*\+\s*uv\s*\+\s*uf",  "RO+UV+UF"),
    (r"ro\s*\+\s*uv",             "RO+UV"),
    (r"ro\s*\+\s*uf",             "RO+UF"),
    (r"\bro\b",                   "RO"),
    (r"\buv\b",                   "UV"),
]

def extract_category(text):
    t = text.lower()
    for pat, label in CAT_PATTERNS:
        if re.search(pat, t):
            return label
    return "RO"

def extract_storage(text):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:litre|liter|l)\b", text, re.I)
    return float(m.group(1)) if m else None

def extract_price(text):
    if not text:
        return None
    text = re.sub(r"[,\s₹Rs.]", "", str(text))
    m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
    return float(m.group(1)) if m else None

def is_water_purifier(item):
    """Filter: only keep water purifier products, not spare parts etc."""
    link = item.get("link","").lower()
    name = item.get("title",{}).get("rendered","").lower()
    # Must be under /water-purifier/ path
    if "/water-purifier/" not in link:
        return False
    # Exclude spare parts, accessories
    exclude = ["spare","filter cartridge","membrane","service kit",
               "pre-filter","adapter","tap","pipe","fitting"]
    if any(x in name for x in exclude):
        return False
    return True

def download_image(url, product_id):
    if not url:
        return ""
    dest = IMAGE_DIR / f"{product_id}.jpg"
    if dest.exists():
        return str(dest)
    try:
        resp = requests.get(url, headers=hdrs(), timeout=15)
        if resp.status_code != 200:
            return ""
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        if img.width < 100 or img.height < 100:
            return ""
        img.thumbnail((1200, 1200))
        img.save(dest, "JPEG", quality=92)
        return str(dest)
    except Exception as e:
        log.debug(f"  img failed: {e}")
        return ""

# ── Scrape product detail page for price + image ──────────────────────
def scrape_aosmith_product_page(session, url):
    """
    Price is in page source as JSON or regex-extractable.
    Image is in JSON-LD or og:image.
    """
    result = {"price": None, "mrp": None, "image_url": "", "availability": "unknown"}
    try:
        r    = session.get(url, headers=hdrs(url), timeout=15)
        if r.status_code != 200:
            return result
        html = r.text
        soup = BeautifulSoup(html, "lxml")

        # ── Price: try multiple sources ───────────────────────────────

        # 1. JSON-LD Product schema
        for sc in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(sc.string or "")
                if data.get("@type") == "Product":
                    offers = data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0]
                    p = offers.get("price") or offers.get("lowPrice")
                    if p:
                        result["price"] = float(str(p).replace(",",""))
                    avail = offers.get("availability","")
                    result["availability"] = ("in_stock"
                                              if "InStock" in avail else "unknown")
                    img = data.get("image","")
                    if isinstance(img, list):
                        img = img[0]
                    if img:
                        result["image_url"] = img
                    break
            except Exception:
                pass

        # 2. Regex in raw HTML (WooCommerce embeds price in page JSON)
        if not result["price"]:
            for pat in [
                r'"price"\s*:\s*"([\d]+)"',
                r'"regular_price"\s*:\s*"([\d]+)"',
                r'class="price"[^>]*>.*?₹\s*([\d,]+)',
                r'"price":"([\d]+)"',
            ]:
                m = re.search(pat, html)
                if m:
                    result["price"] = float(m.group(1).replace(",",""))
                    break

        # 3. MRP pattern
        if not result["mrp"]:
            m = re.search(r'"regular_price"\s*:\s*"([\d]+)"', html)
            if m:
                result["mrp"] = float(m.group(1))

        # ── Image ─────────────────────────────────────────────────────
        if not result["image_url"]:
            # og:image is reliable on WooCommerce
            og = soup.select_one("meta[property='og:image']")
            if og:
                result["image_url"] = og.get("content","")

        if not result["image_url"]:
            # WooCommerce product image
            for sel in ["div.woocommerce-product-gallery img",
                        "img.wp-post-image",
                        "img[class*='product']",
                        "figure.woocommerce-product-gallery__wrapper img"]:
                img_el = soup.select_one(sel)
                if img_el:
                    src = img_el.get("src","")
                    if src and "placeholder" not in src:
                        result["image_url"] = src
                        break

    except Exception as e:
        log.debug(f"  AO Smith page error: {e}")
    return result


# ── Main ──────────────────────────────────────────────────────────────
def scrape_aosmith(seen_ids):
    session = requests.Session()

    # Fetch all products from WP REST API
    # API returns 95 items but we need to paginate (default 10 per page)
    log.info("  [AO Smith] Fetching product list from WP REST API...")
    all_items = []
    for page in range(1, 15):
        url = (f"https://www.aosmithindia.com/wp-json/wp/v2/product"
               f"?per_page=100&page={page}&_fields=id,title,slug,link,status")
        try:
            r = session.get(url, headers=hdrs(), timeout=15)
            if r.status_code == 400:
                break  # no more pages
            if r.status_code != 200:
                log.warning(f"  AO Smith API HTTP {r.status_code} page {page}")
                break
            items = r.json()
            if not items:
                break
            all_items.extend(items)
            log.info(f"  Page {page}: {len(items)} items, total={len(all_items)}")
            if len(items) < 100:
                break
            time.sleep(0.5)
        except Exception as e:
            log.error(f"  API error: {e}")
            break

    log.info(f"  [AO Smith] {len(all_items)} total items from API")

    # Filter to water purifiers only
    purifiers = [i for i in all_items if is_water_purifier(i)]
    log.info(f"  [AO Smith] {len(purifiers)} water purifiers after filter")

    # Scrape each product page for price + image
    products = []
    for i, item in enumerate(purifiers):
        try:
            name = item.get("title",{}).get("rendered","").strip()
            # Decode HTML entities
            name = name.replace("&amp;","&").replace("&#8211;","-").replace("&#038;","&")
            url  = item.get("link","")
            if not name or not url:
                continue

            p_temp = Product(source="aosmith_official", product_url=url).make_id()
            if p_temp.id in seen_ids:
                log.debug(f"  [{i+1}] already in DB: {name[:40]}")
                continue

            log.info(f"  [{i+1}/{len(purifiers)}] {name[:55]}")
            detail = scrape_aosmith_product_page(session, url)

            price = detail["price"]
            mrp   = detail["mrp"]
            disc  = (round((mrp-price)/mrp*100,1)
                     if mrp and price and mrp > price else None)

            # Model: slug is clean e.g. "proplanet-p7" -> "ProPlanet P7"
            slug  = item.get("slug","")
            model = slug.replace("-"," ").title()

            p = Product(
                source       = "aosmith_official",
                brand        = "AO Smith",
                model        = model,
                full_name    = f"AO Smith {name}",
                category     = extract_category(name),
                storage_l    = extract_storage(name),
                price_inr    = price,
                mrp_inr      = mrp,
                discount_pct = disc,
                availability = detail["availability"],
                image_url    = detail["image_url"],
                product_url  = url,
            ).make_id()

            p.local_image = download_image(p.image_url, p.id)
            products.append(p)
            seen_ids.add(p.id)

            log.info(f"    Rs.{price or '?'}  img={'YES' if p.local_image else 'NO'}")
            time.sleep(random.uniform(0.8, 1.5))

        except Exception:
            log.error(traceback.format_exc())

    log.info(f"  [AO Smith] Total new: {len(products)}")
    return products


# ── Standalone entry point ────────────────────────────────────────────
if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY, source TEXT, brand TEXT, model TEXT,
        full_name TEXT, category TEXT, storage_l REAL, capacity_lph REAL,
        price_inr REAL, mrp_inr REAL, discount_pct REAL, rating REAL,
        review_count INTEGER, availability TEXT, image_url TEXT,
        local_image TEXT, product_url TEXT, scraped_at TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON products(source)")
    conn.commit()

    seen_ids = {r[0] for r in conn.execute("SELECT id FROM products")}
    log.info(f"Existing DB: {len(seen_ids)} products")

    products = scrape_aosmith(seen_ids)

    for p in products:
        d     = asdict(p)
        cols  = ", ".join(d.keys())
        holds = ", ".join(["?"] * len(d))
        conn.execute(
            f"INSERT OR REPLACE INTO products ({cols}) VALUES ({holds})",
            list(d.values()))
    conn.commit()

    ao_total = conn.execute(
        "SELECT COUNT(*) FROM products WHERE source='aosmith_official'"
    ).fetchone()[0]
    db_total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()

    print(f"\n  Added     : {len(products)} new products")
    print(f"  AO Smith  : {ao_total} total in DB")
    print(f"  DB total  : {db_total}")
    print(f"  Images    : {len(list(IMAGE_DIR.glob('*.jpg')))} files")