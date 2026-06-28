# """
# scrape_eureka_final.py
# =======================
# Standalone Eureka Forbes / Aquaguard scraper.
# Uses JSON-LD ItemList (no Selenium) to get all product URLs,
# then scrapes each product detail page for price + image.

# Run standalone:
#     python scrape_eureka_final.py

# Or copy scrape_eureka() into scraper_v2.py replacing the old one.
# """

# import re, json, time, random, hashlib, sqlite3, requests, traceback
# from pathlib import Path
# from dataclasses import dataclass, field, asdict
# from typing import Optional
# from io import BytesIO
# from bs4 import BeautifulSoup
# from PIL import Image
# from datetime import datetime

# # ── Paths (same as scraper_v2.py) ────────────────────────────────────
# BASE_DIR  = Path(r"C:\Misc_progs\RO\ro_v2")
# IMAGE_DIR = BASE_DIR / "images"
# DB_PATH   = BASE_DIR / "catalogue_v2.db"
# IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# # ── Logging ──────────────────────────────────────────────────────────
# import logging, io, sys
# def get_log():
#     logger = logging.getLogger("ro_v2")
#     if not logger.handlers:
#         logger.setLevel(logging.DEBUG)
#         fmt  = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
#         utf8 = (io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
#                 errors="replace", line_buffering=True)
#                 if hasattr(sys.stdout, "buffer") else sys.stdout)
#         ch = logging.StreamHandler(stream=utf8)
#         ch.setLevel(logging.INFO)
#         ch.setFormatter(fmt)
#         logger.addHandler(ch)
#     return logger
# log = get_log()

# UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"

# def rand_headers(referer="https://www.eurekaforbes.com/"):
#     return {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
#             "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
#             "Referer": referer, "DNT": "1"}

# # ── Data model (minimal, matches scraper_v2.py) ──────────────────────
# @dataclass
# class Product:
#     id:           str = ""
#     source:       str = ""
#     brand:        str = ""
#     model:        str = ""
#     full_name:    str = ""
#     category:     str = ""
#     storage_l:    Optional[float] = None
#     capacity_lph: Optional[float] = None
#     price_inr:    Optional[float] = None
#     mrp_inr:      Optional[float] = None
#     discount_pct: Optional[float] = None
#     rating:       Optional[float] = None
#     review_count: Optional[int]   = None
#     availability: str = "unknown"
#     image_url:    str = ""
#     local_image:  str = ""
#     product_url:  str = ""
#     scraped_at:   str = field(default_factory=lambda: datetime.now().isoformat())

#     def make_id(self):
#         self.id = hashlib.md5(
#             f"{self.source}{self.product_url}".encode()).hexdigest()[:12]
#         return self

# def extract_category(text):
#     t = text.lower()
#     for pat, label in [
#         (r"ro\s*\+\s*uv\s*\+\s*uf",  "RO+UV+UF"),
#         (r"ro\s*\+\s*uv\s*\+\s*tds", "RO+UV+TDS"),
#         (r"ro\s*\+\s*uv",             "RO+UV"),
#         (r"ro\s*\+\s*uf",             "RO+UF"),
#         (r"\bro\b",                   "RO"),
#     ]:
#         if re.search(pat, t):
#             return label
#     return "UV"

# def extract_price(text):
#     if not text:
#         return None
#     text = re.sub(r"[,\s₹Rs.]", "", text)
#     m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
#     return float(m.group(1)) if m else None

# def extract_storage(text):
#     m = re.search(r"(\d+(?:\.\d+)?)\s*(?:litre|liter|l)\b", text, re.I)
#     return float(m.group(1)) if m else None

# def download_image(url, product_id):
#     if not url:
#         return ""
#     dest = IMAGE_DIR / f"{product_id}.jpg"
#     if dest.exists():
#         return str(dest)
#     try:
#         resp = requests.get(url, headers=rand_headers(), timeout=15)
#         if resp.status_code != 200:
#             return ""
#         img = Image.open(BytesIO(resp.content)).convert("RGB")
#         if img.width < 100 or img.height < 100:
#             return ""
#         img.thumbnail((1200, 1200))
#         img.save(dest, "JPEG", quality=92)
#         return str(dest)
#     except Exception as e:
#         log.debug(f"  img failed: {e}")
#         return ""

# # ── Category pages that have JSON-LD ItemList ────────────────────────
# EUREKA_CATEGORY_URLS = [
#     "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier",
#     "https://www.eurekaforbes.com/c/water-purifiers/uv-water-purifier",
#     "https://www.eurekaforbes.com/c/water-purifiers/stainless-steel-purifier",
#     "https://www.eurekaforbes.com/c/water-purifiers/slim-water-purifier",
#     "https://www.eurekaforbes.com/c/water-purifiers/copper-water-purifier",
#     "https://www.eurekaforbes.com/c/water-purifiers/hot-and-ambient-purifier",
#     "https://www.eurekaforbes.com/c/water-purifiers/alkaline-boost-water-purifier",
# ]

# def get_product_urls_from_category(session, cat_url):
#     """Extract product name+URL pairs from JSON-LD ItemList."""
#     products = []
#     try:
#         r    = session.get(cat_url, headers=rand_headers(), timeout=20)
#         if r.status_code != 200:
#             log.warning(f"  Eureka: HTTP {r.status_code} for {cat_url}")
#             return []
#         soup = BeautifulSoup(r.text, "lxml")
#         for sc in soup.select("script[type='application/ld+json']"):
#             try:
#                 data = json.loads(sc.string or "")
#                 if data.get("@type") == "ItemList":
#                     for item in data.get("itemListElement", []):
#                         raw_url = item.get("url","")
#                         name    = item.get("name","").strip()
#                         if not raw_url or not name:
#                             continue
#                         # Fix double-slash and missing scheme
#                         url = "https://" + raw_url.lstrip("/").replace("//","/",1)
#                         # Normalise: eurekaforbes.com//dp/... -> eurekaforbes.com/dp/...
#                         url = re.sub(r"([a-z])//", r"\1/", url)
#                         products.append({"name": name, "url": url})
#             except Exception:
#                 pass
#     except Exception as e:
#         log.error(f"  Eureka category error {cat_url}: {e}")
#     return products

# def scrape_eureka_product_page(session, url, name):
#     """
#     Scrape a single Eureka Forbes product detail page.
#     Returns dict with price, mrp, image_url.
#     """
#     result = {"price_str": "", "mrp_str": "", "image_url": ""}
#     try:
#         r    = session.get(url, headers=rand_headers(referer=url), timeout=15)
#         if r.status_code != 200:
#             log.debug(f"  Eureka product: HTTP {r.status_code} {url}")
#             return result
#         soup = BeautifulSoup(r.text, "lxml")

#         # ── Price ────────────────────────────────────────────────────
#         # Try JSON-LD Product first (most reliable)
#         for sc in soup.select("script[type='application/ld+json']"):
#             try:
#                 data = json.loads(sc.string or "")
#                 if data.get("@type") == "Product":
#                     offers = data.get("offers", {})
#                     if isinstance(offers, list):
#                         offers = offers[0]
#                     price = offers.get("price","") or offers.get("lowPrice","")
#                     if price:
#                         result["price_str"] = str(price)
#                     # Image from JSON-LD
#                     img = data.get("image","")
#                     if isinstance(img, list):
#                         img = img[0]
#                     if img:
#                         result["image_url"] = img
#                     break
#             except Exception:
#                 pass

#         # Fallback price: span.price or [class*=price]
#         if not result["price_str"]:
#             for sel in ["span.price","[class*='final-price'] span",
#                         "[class*='selling-price']","[data-price-type='finalPrice']"]:
#                 el = soup.select_one(sel)
#                 if el:
#                     txt = el.get_text(strip=True)
#                     if re.search(r"\d{3,}", txt):
#                         result["price_str"] = txt
#                         break

#         # MRP / strikethrough price
#         for sel in ["[class*='old-price']","[class*='regular-price']",
#                     "[data-price-type='oldPrice']","s.price"]:
#             el = soup.select_one(sel)
#             if el:
#                 txt = el.get_text(strip=True)
#                 if re.search(r"\d{3,}", txt):
#                     result["mrp_str"] = txt
#                     break

#         # ── Image ────────────────────────────────────────────────────
#         if not result["image_url"]:
#             # Gallery main image
#             for sel in [
#                 "img.gallery-placeholder__image",
#                 "img[class*='product-image-photo']",
#                 "div.fotorama__img img",
#                 "img[class*='gallery']",
#                 "div[class*='gallery'] img",
#                 "img[itemprop='image']",
#             ]:
#                 img_el = soup.select_one(sel)
#                 if img_el:
#                     src = (img_el.get("src","") or
#                            img_el.get("data-src","")).strip()
#                     if src and "placeholder" not in src and len(src) > 10:
#                         result["image_url"] = src
#                         break

#         # Open Graph image as last resort
#         if not result["image_url"]:
#             og = soup.select_one("meta[property='og:image']")
#             if og:
#                 result["image_url"] = og.get("content","")

#     except Exception as e:
#         log.debug(f"  Eureka product page error: {e}\n{traceback.format_exc()}")

#     return result


# def scrape_eureka(seen_ids):
#     """
#     Full Eureka Forbes / Aquaguard scraper.
#     Pure requests, no Selenium.
#     """
#     session = requests.Session()

#     # Step 1: warm up session with homepage (gets cookies)
#     log.info("  [Eureka] Warming up session...")
#     session.get("https://www.eurekaforbes.com/", timeout=15)
#     time.sleep(1)

#     # Step 2: collect all product name+URL from JSON-LD across all categories
#     all_items = {}  # url -> name (deduplicates across categories)
#     for cat_url in EUREKA_CATEGORY_URLS:
#         log.info(f"  [Eureka] Collecting from {cat_url.split('/')[-1]}")
#         items = get_product_urls_from_category(session, cat_url)
#         for item in items:
#             all_items[item["url"]] = item["name"]
#         log.info(f"    {len(items)} products, {len(all_items)} unique total")
#         time.sleep(random.uniform(1.0, 2.0))

#     log.info(f"  [Eureka] {len(all_items)} unique products found across all categories")

#     # Step 3: scrape each product detail page
#     products = []
#     for i, (url, name) in enumerate(all_items.items()):
#         try:
#             log.info(f"  [{i+1}/{len(all_items)}] {name[:55]}")
#             detail = scrape_eureka_product_page(session, url, name)

#             price = extract_price(detail["price_str"])
#             mrp   = extract_price(detail["mrp_str"])

#             p = Product(
#                 source       = "eureka_official",
#                 brand        = "Eureka Forbes",
#                 model        = name,
#                 full_name    = name,
#                 category     = extract_category(name),
#                 storage_l    = extract_storage(name),
#                 price_inr    = price,
#                 mrp_inr      = mrp,
#                 discount_pct = (round((mrp-price)/mrp*100,1)
#                                 if mrp and price and mrp > price else None),
#                 image_url    = detail["image_url"],
#                 product_url  = url,
#             ).make_id()

#             if p.id in seen_ids:
#                 log.debug(f"    already in DB, skipping")
#                 continue

#             p.local_image = download_image(p.image_url, p.id)
#             products.append(p)
#             seen_ids.add(p.id)
#             log.info(f"    price=Rs.{price or '?'}  img={'YES' if p.local_image else 'NO'}")
#             time.sleep(random.uniform(0.8, 1.5))

#         except Exception:
#             log.debug(traceback.format_exc())

#     log.info(f"  [Eureka Forbes/Aquaguard] Total: {len(products)}")
#     return products


# # ── Standalone runner ────────────────────────────────────────────────
# if __name__ == "__main__":
#     # Connect to existing DB
#     conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
#     conn.execute("""CREATE TABLE IF NOT EXISTS products (
#         id TEXT PRIMARY KEY, source TEXT, brand TEXT, model TEXT,
#         full_name TEXT, category TEXT, storage_l REAL, capacity_lph REAL,
#         price_inr REAL, mrp_inr REAL, discount_pct REAL, rating REAL,
#         review_count INTEGER, availability TEXT, image_url TEXT,
#         local_image TEXT, product_url TEXT, scraped_at TEXT)""")
#     conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON products(source)")
#     conn.commit()

#     seen_ids = {r[0] for r in conn.execute("SELECT id FROM products")}
#     products = scrape_eureka(seen_ids)

#     for p in products:
#         d = asdict(p)
#         conn.execute(
#             f"INSERT OR REPLACE INTO products ({','.join(d)}) "
#             f"VALUES ({','.join(['?']*len(d))})",
#             list(d.values()))
#     conn.commit()

#     total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
#     eureka = conn.execute(
#         "SELECT COUNT(*) FROM products WHERE source='eureka_official'"
#     ).fetchone()[0]
#     conn.close()

#     print(f"\n  Added {len(products)} Eureka Forbes products")
#     print(f"  Eureka total in DB: {eureka}")
#     print(f"  DB total: {total}")
"""
scrape_eureka_final.py - Eureka Forbes / Aquaguard scraper
=============================================================
Zero Selenium. Pure requests + JSON.

Stage 1: category pages -> JSON-LD ItemList -> product name + URL
Stage 2: each product page -> pageProps JSON -> price/mrp
                           -> JSON-LD Product -> image URL

Run standalone:
    python scrape_eureka_final.py
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

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR  = Path(r"C:\Misc_progs\RO\ro_v2")
IMAGE_DIR = BASE_DIR / "images"
DB_PATH   = BASE_DIR / "catalogue_v2.db"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# ── Logger ────────────────────────────────────────────────────────────
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

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":      UA,
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
        "Referer":         "https://www.google.co.in/",
        "DNT":             "1",
    })
    # Warm up - gets Azure gateway cookies required to avoid 403
    s.get("https://www.eurekaforbes.com/", timeout=15)
    time.sleep(1)
    return s

# ── Data model ────────────────────────────────────────────────────────
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

# ── Helpers ───────────────────────────────────────────────────────────
CAT_PATTERNS = [
    (r"ro\s*\+\s*uv\s*\+\s*uf",  "RO+UV+UF"),
    (r"ro\s*\+\s*uv\s*\+\s*tds", "RO+UV+TDS"),
    (r"ro\s*\+\s*uv",             "RO+UV"),
    (r"ro\s*\+\s*uf",             "RO+UF"),
    (r"\bro\b",                   "RO"),
]

def extract_category(text):
    t = text.lower()
    for pat, label in CAT_PATTERNS:
        if re.search(pat, t):
            return label
    return "UV"

def extract_storage(text):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:litre|liter|l)\b", text, re.I)
    return float(m.group(1)) if m else None

def download_image(url, product_id):
    if not url:
        return ""
    dest = IMAGE_DIR / f"{product_id}.jpg"
    if dest.exists():
        return str(dest)
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=15)
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

# ── Stage 1: collect product URLs from JSON-LD ItemList ───────────────
CATEGORY_URLS = [
    "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/uv-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/copper-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/stainless-steel-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/slim-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/hot-and-ambient-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/alkaline-boost-water-purifier",
]

def collect_product_urls(session):
    """
    Parse JSON-LD ItemList from each category page.
    Returns dict: {product_url: name}
    """
    items = {}
    for cat_url in CATEGORY_URLS:
        log.info(f"  [Eureka] Collecting: .../{cat_url.split('/')[-1]}")
        try:
            r    = session.get(cat_url, timeout=20)
            soup = BeautifulSoup(r.text, "lxml")
            for sc in soup.select("script[type='application/ld+json']"):
                try:
                    data = json.loads(sc.string or "")
                    if data.get("@type") != "ItemList":
                        continue
                    for item in data.get("itemListElement", []):
                        raw = item.get("url","")
                        name = item.get("name","").strip()
                        if not raw or not name:
                            continue
                        # Fix: "www.eurekaforbes.com//dp/..." -> proper URL
                        url = "https://" + raw.lstrip("/")
                        url = re.sub(r"([a-z\.])//", r"\1/", url)
                        if url not in items:
                            items[url] = name
                except Exception:
                    pass
            log.info(f"    {len(items)} unique products so far")
        except Exception as e:
            log.error(f"  Category error: {e}")
        time.sleep(random.uniform(1.0, 2.0))
    return items

# ── Stage 2: scrape each product detail page ──────────────────────────
def scrape_product_page(session, url):
    """
    Returns dict with: price, mrp, disc_pct, image_url, brand, availability
    Uses pageProps JSON (price) + JSON-LD Product (image) — no CSS selectors.
    """
    result = {
        "price":        None,
        "mrp":          None,
        "disc_pct":     None,
        "image_url":    "",
        "brand":        "Eureka Forbes",
        "availability": "unknown",
    }
    try:
        r    = session.get(url, timeout=15)
        if r.status_code != 200:
            log.debug(f"  product page HTTP {r.status_code}: {url}")
            return result
        soup = BeautifulSoup(r.text, "lxml")

        # ── Price from pageProps (most accurate - direct from backend) ──
        for sc in soup.find_all("script"):
            txt = sc.string or ""
            if "productDetail" in txt and "sellingPrice" in txt:
                try:
                    data   = json.loads(txt)
                    detail = data["props"]["pageProps"]["productDetail"]
                    price_obj = detail.get("price", {})

                    result["price"]    = price_obj.get("sellingPrice")
                    result["mrp"]      = price_obj.get("mrp")
                    result["disc_pct"] = price_obj.get("discPercent")

                    # Availability from quantity
                    qty = detail.get("quantity", {})
                    if qty.get("max", 0) > 0:
                        result["availability"] = "in_stock"
                except Exception:
                    log.debug(traceback.format_exc())
                break

        # ── Image from JSON-LD Product (clean full URL) ──────────────
        for sc in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(sc.string or "")
                if data.get("@type") != "Product":
                    continue

                # image field is a direct full URL
                img = data.get("image","")
                if isinstance(img, list):
                    img = img[0]
                if img:
                    result["image_url"] = img

                # Brand
                brand = data.get("brand",{}).get("name","")
                if brand:
                    result["brand"] = brand

                # Price fallback if pageProps failed
                if not result["price"]:
                    offers = data.get("offers",{})
                    if isinstance(offers, list):
                        offers = offers[0]
                    p = offers.get("price")
                    if p:
                        result["price"] = float(p)
                    avail = offers.get("availability","")
                    if "InStock" in avail:
                        result["availability"] = "in_stock"
                break
            except Exception:
                pass

    except Exception as e:
        log.debug(f"  product page error: {e}")

    return result


# ── Main scraper ──────────────────────────────────────────────────────
def scrape_eureka(seen_ids):
    session = make_session()

    # Stage 1: collect all product URLs
    log.info("  [Eureka] Stage 1: collecting product URLs from category pages...")
    url_to_name = collect_product_urls(session)
    log.info(f"  [Eureka] Found {len(url_to_name)} unique products")

    # Stage 2: scrape each product page
    log.info("  [Eureka] Stage 2: scraping product pages for price + image...")
    products = []

    for i, (url, name) in enumerate(url_to_name.items()):
        try:
            p_temp = Product(source="eureka_official", product_url=url).make_id()
            if p_temp.id in seen_ids:
                log.debug(f"  [{i+1}] already in DB: {name[:40]}")
                continue

            log.info(f"  [{i+1}/{len(url_to_name)}] {name[:55]}")
            detail = scrape_product_page(session, url)

            price = detail["price"]
            mrp   = detail["mrp"]
            disc  = detail["disc_pct"]
            if not disc and price and mrp and mrp > price:
                disc = round((mrp - price) / mrp * 100, 1)

            p = Product(
                source       = "eureka_official",
                brand        = detail["brand"],
                model        = name,
                full_name    = name,
                category     = extract_category(name),
                storage_l    = extract_storage(name),
                price_inr    = float(price) if price else None,
                mrp_inr      = float(mrp)   if mrp   else None,
                discount_pct = float(disc)  if disc  else None,
                availability = detail["availability"],
                image_url    = detail["image_url"],
                product_url  = url,
            ).make_id()

            p.local_image = download_image(p.image_url, p.id)
            products.append(p)
            seen_ids.add(p.id)

            log.info(f"    Rs.{price or '?'}  mrp={mrp or '?'}"
                     f"  img={'YES' if p.local_image else 'NO'}")
            time.sleep(random.uniform(0.8, 1.5))

        except Exception:
            log.error(f"  Error on {url}: {traceback.format_exc()}")

    log.info(f"  [Eureka Forbes/Aquaguard] Total new: {len(products)}")
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

    products = scrape_eureka(seen_ids)

    for p in products:
        d     = asdict(p)
        cols  = ", ".join(d.keys())
        holds = ", ".join(["?"] * len(d))
        conn.execute(
            f"INSERT OR REPLACE INTO products ({cols}) VALUES ({holds})",
            list(d.values()))
    conn.commit()

    eureka_total = conn.execute(
        "SELECT COUNT(*) FROM products WHERE source='eureka_official'"
    ).fetchone()[0]
    db_total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()

    print(f"\n  Added     : {len(products)} new products")
    print(f"  Eureka DB : {eureka_total} total")
    print(f"  DB total  : {db_total}")
    print(f"  Images    : {len(list(IMAGE_DIR.glob('*.jpg')))} files")