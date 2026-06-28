"""
scraper_v2.py - RO Catalogue V2
Sources: Livpure, V-Guard, Faber (Shopify JSON), Kent (BS4), LG + Eureka Forbes (Selenium)
Usage:
  python scraper_v2.py --scrape                   # all sources
  python scraper_v2.py --scrape --source kent     # single source
  python scraper_v2.py --status
  python scraper_v2.py --export
"""

import re, io, sys, time, random, hashlib, sqlite3, logging, requests
import traceback, argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from urllib.parse import urljoin
from io import BytesIO
from collections import Counter
from bs4 import BeautifulSoup
from PIL import Image

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

BASE_DIR  = Path(r"C:\Misc_progs\RO\ro_v2")
IMAGE_DIR = BASE_DIR / "images"
DB_PATH   = BASE_DIR / "catalogue_v2.db"
LOG_DIR   = BASE_DIR / "logs"
for d in [BASE_DIR, IMAGE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def setup_logger():
    logger = logging.getLogger("ro_v2")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt  = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    utf8 = (io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
            errors="replace", line_buffering=True)
            if hasattr(sys.stdout, "buffer") else sys.stdout)
    ch = logging.StreamHandler(stream=utf8)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    fh = logging.FileHandler(
        LOG_DIR / f"scrape_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

log = setup_logger()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 Version/17.3 Safari/605.1.15",
]

def rand_headers():
    return {"User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Referer": "https://www.google.co.in/", "DNT": "1"}

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

CATEGORY_PATTERNS = [
    (r"ro\s*\+\s*uv\s*\+\s*uf",  "RO+UV+UF"),
    (r"ro\s*\+\s*uv\s*\+\s*tds", "RO+UV+TDS"),
    (r"ro\s*\+\s*uv",               "RO+UV"),
    (r"ro\s*\+\s*uf",               "RO+UF"),
    (r"\bro\b",                       "RO"),
]

def extract_category(text):
    t = text.lower()
    for pat, label in CATEGORY_PATTERNS:
        if re.search(pat, t):
            return label
    return "RO"

def extract_price(text):
    if not text:
        return None
    text = re.sub(r"[,\s]", "", text.replace("Rs.","").replace("INR",""))
    m = re.search(r"(\d+(?:\.\d{1,2})?)", text)
    return float(m.group(1)) if m else None

def extract_storage(text):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:litre|liter|l)\b", text, re.I)
    return float(m.group(1)) if m else None

def is_purifier(name, shopify_product_type=""):
    spt = shopify_product_type.lower()
    if any(w in spt for w in ["water purifier", "ro purifier", "water filter"]):
        acc = ["cartridge","membrane gpd","sediment filter","spun filter",
               "service kit","solenoid","uv lamp","spanner"]
        return not any(w in name.lower() for w in acc)
    name_l = name.lower()
    purifier_words = ["water purifier","ro purifier","ro system","ro unit","ro water",
                      "reverse osmosis","aquaguard","aquasure","health guard"]
    has_purifier = any(w in name_l for w in purifier_words)
    acc_words = ["cartridge","membrane gpd","sediment","spun filter","carbon block",
                 "service kit","solenoid","tds meter","uv lamp","filter housing",
                 "spanner","o-ring","power supply"]
    return has_purifier and not any(w in name_l for w in acc_words)

def best_img(img_el):
    if not img_el:
        return ""
    for attr in ["data-zoom-image","data-src-large","data-original",
                 "data-src","data-lazy","src"]:
        val = img_el.get(attr, "").strip()
        if val and "placeholder" not in val and "base64" not in val:
            return val
    return ""

def download_image(url, product_id):
    if not url:
        return ""
    dest = IMAGE_DIR / f"{product_id}.jpg"
    if dest.exists():
        return str(dest)
    try:
        resp = requests.get(url, headers=rand_headers(), timeout=15)
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

class DB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY, source TEXT, brand TEXT, model TEXT,
            full_name TEXT, category TEXT, storage_l REAL, capacity_lph REAL,
            price_inr REAL, mrp_inr REAL, discount_pct REAL, rating REAL,
            review_count INTEGER, availability TEXT, image_url TEXT,
            local_image TEXT, product_url TEXT, scraped_at TEXT)""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON products(source)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_brand  ON products(brand)")
        self.conn.commit()

    def seen_ids(self):
        return {r[0] for r in self.conn.execute("SELECT id FROM products")}

    def insert(self, p):
        d = asdict(p)
        cols  = ", ".join(d.keys())
        holds = ", ".join(["?"] * len(d))
        self.conn.execute(
            f"INSERT OR REPLACE INTO products ({cols}) VALUES ({holds})",
            list(d.values()))
        self.conn.commit()

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    def all(self):
        cur = self.conn.execute("SELECT * FROM products")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def close(self):
        self.conn.close()

def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    # Find Chrome binary - check common Windows locations
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\aryan\AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    for path in chrome_paths:
        if Path(path).exists():
            opts.binary_location = path
            break

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts)

def slow_scroll(driver, times=5, pause=1.0):
    for _ in range(times):
        driver.execute_script("window.scrollBy(0, window.innerHeight)")
        time.sleep(pause)

def click_load_more(driver, max_clicks=8):
    sel = ("button[class*=load-more],a[class*=load-more],"
           "button[class*=LoadMore],button[class*=show-more]")
    for _ in range(max_clicks):
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed():
                driver.execute_script("arguments[0].click()", btn)
                time.sleep(2)
            else:
                break
        except Exception:
            break

SHOPIFY_SOURCES = [
    {"name":"Livpure", "source":"livpure_official",
     "base":"https://livpure.com",    "handle":"water-purifier"},
    {"name":"V-Guard", "source":"vguard_official",
     "base":"https://vguard.com",     "handle":"water-purifier"},
    {"name":"Faber",   "source":"faber_official",
     "base":"https://faberindia.com", "handle":"water-purifiers"},
]

def scrape_shopify(cfg, seen_ids):
    products = []
    session  = requests.Session()
    for page in range(1, 10):
        url = (f"{cfg['base']}/collections/{cfg['handle']}"
               f"/products.json?limit=250&page={page}")
        log.info(f"  [Shopify:{cfg['name']}] page {page}")
        try:
            resp  = session.get(url, headers=rand_headers(), timeout=20)
            if resp.status_code != 200:
                break
            items = resp.json().get("products", [])
            if not items:
                break
            accepted = 0
            for item in items:
                name  = item.get("title","").strip()
                ptype = item.get("product_type","")
                if not is_purifier(name, ptype):
                    continue
                variants = item.get("variants", [])
                prices   = [float(v["price"]) for v in variants if v.get("price")]
                compares = [float(v["compare_at_price"]) for v in variants
                            if v.get("compare_at_price")]
                price    = min(prices)   if prices   else None
                mrp      = min(compares) if compares else None
                avail    = any(v.get("available", False) for v in variants)
                images   = item.get("images", [])
                img_url  = ""
                if images:
                    img_url = re.sub(r"_\d+x\d*\.", "_1200x.", images[0]["src"])
                link = f"{cfg['base']}/products/{item.get('handle','')}"
                body = BeautifulSoup(item.get("body_html",""), "lxml").get_text(" ")
                p = Product(
                    source       = cfg["source"], brand = cfg["name"],
                    model        = name, full_name = name,
                    category     = extract_category(f"{name} {chr(32).join(item.get('tags',[]))}"),
                    storage_l    = extract_storage(f"{name} {body}"),
                    price_inr    = price, mrp_inr = mrp,
                    discount_pct = (round((mrp-price)/mrp*100,1)
                                    if mrp and price and mrp > price else None),
                    availability = "in_stock" if avail else "out_of_stock",
                    image_url    = img_url, product_url = link,
                ).make_id()
                if p.id in seen_ids:
                    continue
                p.local_image = download_image(p.image_url, p.id)
                products.append(p)
                seen_ids.add(p.id)
                accepted += 1
            log.info(f"    {len(items)} items -> {accepted} accepted")
            if len(items) < 250:
                break
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            log.error(f"  Shopify error: {e}")
            break
    log.info(f"  [{cfg['name']}] Total: {len(products)}")
    return products

KENT_CATEGORY_URLS = [
    "https://www.kent.co.in/water-purifiers/ro/",
    "https://www.kent.co.in/water-purifiers/ro/limited/",
    "https://www.kent.co.in/water-purifiers/uv/",
    "https://www.kent.co.in/water-purifiers/gravity-uf/",
]

# Products to explicitly exclude (not water purifiers)
KENT_EXCLUDE_PATHS = [
    "/commercial/", "/pitcher", "/nhm/", "/water-softener",
    "/cooking", "/air-purifier", "/vacuum", "/healthy-cookware",
    "/disinfectant", "/steam-iron", "/humidifier",
]

def _is_kent_purifier_url(url):
    if not "/water-purifiers/" in url:
        return False
    if any(x in url for x in KENT_EXCLUDE_PATHS):
        return False
    # Product pages always have 'kent-' in the final path segment
    # e.g. /water-purifiers/ro/kent-grand-plus
    # Category pages don't: /water-purifiers/ro/limited/
    slug = url.rstrip("/").split("/")[-1]
    return slug.startswith("kent-") or "-kent-" in slug

def scrape_kent_product_page(session, url):
    """Scrape a Kent product detail page. Returns dict or {}."""
    try:
        resp = session.get(url, headers=rand_headers(), timeout=15)
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "lxml")

        # Name: h1 is most reliable
        name = ""
        for sel in ["h1.page-title span", "h1.product-name",
                    ".product-info-main h1", "h1"]:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if len(name) > 5:
                    break
        if not name:
            title = soup.find("title")
            if title:
                name = title.get_text().split("|")[0].strip()

        # Price
        price_str = ""
        for sel in ["span.price", ".product-info-price span.price",
                    "[data-price-type='finalPrice'] span.price"]:
            el = soup.select_one(sel)
            if el:
                price_str = el.get_text(strip=True)
                if price_str:
                    break

        # Image - three sources in priority order:
        # 1. img#image (hidden high-res enlarge view)
        # 2. picture source srcset in div.bnr-img
        # 3. Any img under /images/ro/ or /images/water-purifier/
        img_url = ""

        img = soup.select_one("img#image[src]")
        if img:
            src = img["src"]
            img_url = ("https://www.kent.co.in" + src
                       if src.startswith("/") else src)

        if not img_url:
            pic = soup.select_one("div.bnr-img picture source[srcset]")
            if pic:
                srcset = pic["srcset"].split(",")[0].strip().split(" ")[0]
                if srcset:
                    img_url = ("https://www.kent.co.in" + srcset
                               if srcset.startswith("/") else srcset)

        if not img_url:
            for img_el in soup.select("img[src]"):
                src = img_el.get("src","")
                if src and ("/images/ro/" in src or
                            "/images/water-purifier" in src or
                            "/images/nhm/" in src):
                    img_url = ("https://www.kent.co.in" + src
                               if src.startswith("/") else src)
                    break

        return {"name": name, "price_str": price_str, "img_url": img_url}

    except Exception as e:
        log.debug(f"  Kent detail page error {url}: {e}")
        return {}


def scrape_kent(seen_ids):
    if not SELENIUM_OK:
        log.error("  [Kent] Selenium not available")
        return []

    product_urls = set()
    session      = requests.Session()
    driver       = make_driver()

    try:
        for cat_url in KENT_CATEGORY_URLS:
            log.info(f"  [Kent] Rendering {cat_url}")
            driver.get(cat_url)

            # Wait for JS-rendered product cards
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "li.productlistDiv")))
                log.info("  Kent: productlistDiv loaded")
            except Exception:
                log.warning("  Kent: productlistDiv wait timed out")

            slow_scroll(driver, times=4, pause=0.8)
            soup  = BeautifulSoup(driver.page_source, "lxml")

            # Extract product URLs from rendered cards
            cards = soup.select("li.productlistDiv")
            log.info(f"  Kent: {len(cards)} productlistDiv cards")
            for card in cards:
                for a in card.find_all("a", href=True):
                    href = a["href"]
                    if _is_kent_purifier_url(href):
                        full = (urljoin("https://www.kent.co.in", href)
                                if href.startswith("/") else href)
                        product_urls.add(full)

            # Also collect from nav links as backup seed
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if _is_kent_purifier_url(href):
                    parts = [p for p in href.strip("/").split("/") if p]
                    # Only 3-segment paths are product pages, not categories
                    if len(parts) >= 3:
                        full = (urljoin("https://www.kent.co.in", href)
                                if href.startswith("/") else href)
                        product_urls.add(full)

            log.info(f"  Kent: {len(product_urls)} unique product URLs so far")
            time.sleep(random.uniform(1.5, 2.5))

    finally:
        driver.quit()

    log.info(f"  [Kent] Scraping {len(product_urls)} product detail pages...")
    products = []

    for i, url in enumerate(sorted(product_urls)):
        try:
            data = scrape_kent_product_page(session, url)
            if not data or not data.get("name"):
                log.debug(f"  Kent: no name from {url}")
                continue

            name = data["name"]
            # URL is already under /water-purifiers/ so skip purifier keyword check
            # Just reject obvious non-purifier page titles
            if not name or len(name) < 5:
                continue
            junk_titles = ["water purifiers", "ro water purifiers", "uv water purifiers",
                           "gravity water purifiers", "limited stock", "bring home",
                           "world's best", "explore", "view all"]
            if any(name.lower().startswith(j) for j in junk_titles):
                log.debug(f"  Kent: skipping page heading '{name}'")
                continue
            p = Product(
                source      = "kent_official",
                brand       = "Kent",
                model       = name,
                full_name   = name,
                category    = extract_category(name),
                storage_l   = extract_storage(name),
                price_inr   = extract_price(data.get("price_str","")),
                image_url   = data.get("img_url",""),
                product_url = url,
            ).make_id()

            if p.id in seen_ids:
                continue

            p.local_image = download_image(p.image_url, p.id)
            products.append(p)
            seen_ids.add(p.id)
            log.info(f"  [{i+1}/{len(product_urls)}] + {name[:55]}"
                     f"  img={'YES' if p.local_image else 'NO'}")
            time.sleep(random.uniform(0.5, 1.2))

        except Exception:
            log.debug(traceback.format_exc())

    log.info(f"  [Kent] Total: {len(products)}")
    return products
LG_URL = "https://www.lg.com/in/water-purifiers/?ec_model_status_code=Active"

def scrape_lg(seen_ids):
    if not SELENIUM_OK:
        log.error("  [LG] Selenium not available")
        return []
    products = []
    driver   = make_driver()
    try:
        log.info(f"  [LG] {LG_URL}")
        driver.get(LG_URL)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "li.c-product-list__item")))
            log.info("  LG: cards loaded")
        except Exception:
            log.warning("  LG: wait timed out, parsing anyway")

        slow_scroll(driver, times=6, pause=1.2)
        click_load_more(driver, max_clicks=8)
        time.sleep(1)

        soup  = BeautifulSoup(driver.page_source, "lxml")
        cards = soup.select("li.c-product-list__item")
        log.info(f"  LG: {len(cards)} cards found")

        for card in cards:
            try:
                # Full product name (clean, no badge text like CASHBACK/BEST SELLER)
                name_el = card.select_one("div.neo-card--ufn")
                name    = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue

                # Model number e.g. WW184ETC
                model_el   = card.select_one("div.c-product-item__sku")
                model_code = model_el.get_text(strip=True) if model_el else ""

                # Selling price e.g. "₹29190"
                price_el  = card.select_one("span.cell-price")
                price_str = price_el.get_text(strip=True) if price_el else ""

                # MRP (strikethrough) e.g. "₹39299"
                mrp_el    = card.select_one("span.cell-after")
                mrp_str   = mrp_el.get_text(strip=True) if mrp_el else ""

                # Rating "4.6(5)" -> 4.6 rating, 5 reviews
                rating, reviews = None, None
                rat_el = card.select_one(
                    "div.c-product-item__rating--number")
                if rat_el:
                    m = re.match(r"([\d.]+)\((\d+)\)",
                                 rat_el.get_text(strip=True))
                    if m:
                        rating  = float(m.group(1))
                        reviews = int(m.group(2))

                # Image: src is truncated in listing e.g.
                # /content/dam/.../ww184etc/ww184etc-Basic-450.
                # Append .jpg and replace -450 with -1600 for high-res
                img_url = ""
                img_el  = card.select_one("img.cmp-image__image")
                if img_el:
                    src = (img_el.get("src","") or
                           img_el.get("data-src","")).strip()
                    if src:
                        # Ensure extension
                        if not re.search(r"\.\w{3,4}$", src):
                            src = src + ".jpg"
                        # Upgrade resolution: -450 or -450-1v -> -1600
                        src = re.sub(r"-(\d+)(-\w+)?(\.\w+)$",
                                     r"-1600\3", src)
                        img_url = ("https://www.lg.com" + src
                                   if src.startswith("/") else src)

                # Link: button.btn-learn carries href (not an <a> tag)
                link = ""
                btn  = card.select_one("button.btn-learn")
                if btn and btn.get("href"):
                    href = btn["href"]
                    link = (urljoin("https://www.lg.com", href)
                            if href.startswith("/") else href)
                # Fallback: a.c-image href
                if not link:
                    a_el = card.select_one("a.c-image[href]")
                    if a_el:
                        href = a_el["href"]
                        link = (urljoin("https://www.lg.com", href)
                                if href.startswith("/") else href)

                price = extract_price(price_str)
                mrp   = extract_price(mrp_str)

                p = Product(
                    source       = "lg_official",
                    brand        = "LG",
                    model        = model_code,
                    full_name    = name,
                    category     = extract_category(name),
                    storage_l    = extract_storage(name),
                    price_inr    = price,
                    mrp_inr      = mrp,
                    discount_pct = (round((mrp-price)/mrp*100,1)
                                    if mrp and price and mrp > price else None),
                    rating       = rating,
                    review_count = reviews,
                    image_url    = img_url,
                    product_url  = link or LG_URL,
                ).make_id()

                if p.id in seen_ids:
                    continue

                p.local_image = download_image(p.image_url, p.id)
                products.append(p)
                seen_ids.add(p.id)
                log.info(f"    + {name[:55]}  [{model_code}]"
                         f"  img={'YES' if p.local_image else 'NO'}")

            except Exception:
                log.debug(traceback.format_exc())

    finally:
        driver.quit()

    log.info(f"  [LG] Total: {len(products)}")
    return products

EUREKA_CATEGORIES = [
    "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/uv-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/stainless-steel-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/slim-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/copper-water-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/hot-and-ambient-purifier",
    "https://www.eurekaforbes.com/c/water-purifiers/alkaline-boost-water-purifier",
]

def parse_eureka_cards(soup, page_url, seen_ids):
    products = []
    cards    = []
    for sel in ["div.product-item-info","li.item.product",
                "div[class*=ProductCard]","div[class*=product-card]",
                "li[class*=product-item]","article[class*=product]"]:
        cards = soup.select(sel)
        if len(cards) > 1:
            break
    log.info(f"    Eureka: {len(cards)} cards on .../{page_url.split('/')[-1]}")
    for card in cards:
        try:
            name_el = (card.select_one("a.product-item-link") or
                       card.select_one("strong.product-item-name") or
                       card.select_one("[class*=product-name]") or
                       card.select_one("h3 a") or card.select_one("a[title]"))
            if not name_el:
                continue
            name = (name_el.get_text(strip=True) or
                    name_el.get("title","")).strip()
            if not name:
                continue
            link_el  = card.select_one("a[href]")
            link     = (urljoin("https://www.eurekaforbes.com", link_el["href"])
                        if link_el else page_url)
            price_el  = (card.select_one("span.price") or
                         card.select_one("[class*=price]"))
            price_str = price_el.get_text(strip=True) if price_el else ""
            mrp_el    = card.select_one("[class*=old-price],[class*=regular-price]")
            mrp_str   = mrp_el.get_text(strip=True) if mrp_el else ""
            img_url   = ""
            img_el    = card.select_one("img")
            if img_el:
                img_url = best_img(img_el)
                if img_url and img_url.startswith("/"):
                    img_url = "https://www.eurekaforbes.com" + img_url
            p = Product(
                source="eureka_official", brand="Eureka Forbes",
                model=name, full_name=name,
                category=extract_category(name), storage_l=extract_storage(name),
                price_inr=extract_price(price_str), mrp_inr=extract_price(mrp_str),
                image_url=img_url, product_url=link,
            ).make_id()
            if p.id in seen_ids:
                continue
            if p.mrp_inr and p.price_inr and p.mrp_inr > p.price_inr:
                p.discount_pct = round((p.mrp_inr-p.price_inr)/p.mrp_inr*100, 1)
            p.local_image = download_image(p.image_url, p.id)
            products.append(p)
            seen_ids.add(p.id)
            log.info(f"    + {name[:55]}  img={'YES' if p.local_image else 'NO'}")
        except Exception:
            log.debug(traceback.format_exc())
    return products

    if not SELENIUM_OK:
        log.error("  [Eureka] Selenium not available")
        return []
    products = []
    driver   = make_driver()
    try:
        for cat_url in EUREKA_CATEGORIES:
            log.info(f"  [Eureka] {cat_url}")
            driver.get(cat_url)
            loaded = False
            for sel in ["div.product-item-info","li.item.product","div[class*=ProductCard]"]:
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    loaded = True
                    break
                except Exception:
                    continue
            if not loaded:
                log.warning(f"  Eureka: timed out on {cat_url}")
            slow_scroll(driver, times=4, pause=0.8)
            click_load_more(driver, max_clicks=10)
            soup = BeautifulSoup(driver.page_source, "lxml")
            new  = parse_eureka_cards(soup, cat_url, seen_ids)
            products.extend(new)
            log.info(f"    {len(new)} new from this category")
            time.sleep(random.uniform(2.0, 3.5))
    finally:
        driver.quit()
    log.info(f"  [Eureka Forbes] Total: {len(products)}")
    return products
EUREKA_SEARCH_QUERIES = [
    "ro+water+purifier",
    "aquaguard+ro",
    "aquaguard+uv",
    "aquasure",
    "copper+water+purifier",
    "stainless+steel+purifier",
    "slim+water+purifier",
]

def scrape_eureka(seen_ids):
    if not SELENIUM_OK:
        log.error("  [Eureka] Selenium not available")
        return []

    products = []
    driver   = make_driver()

    try:
        for query in EUREKA_SEARCH_QUERIES:
            url = f"https://www.eurekaforbes.com/search?q={query}&type=product"
            log.info(f"  [Eureka] Searching: {query.replace('+', ' ')}")
            driver.get(url)

            # Search pages load more reliably than category pages
            loaded = False
            for sel in ["div.product-item-info",
                        "li.item.product",
                        "ol.products",
                        "div[class*='product-item']"]:
                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, sel)))
                    loaded = True
                    log.info(f"  Eureka: loaded with '{sel}'")
                    break
                except Exception:
                    continue

            if not loaded:
                log.warning(f"  Eureka: timed out for query '{query}'")

            slow_scroll(driver, times=3, pause=0.8)
            soup  = BeautifulSoup(driver.page_source, "lxml")

            # Find product cards
            cards = []
            for sel in ["div.product-item-info",
                        "li.item.product",
                        "div[class*='ProductCard']",
                        "div[class*='product-card']",
                        "li[class*='product-item']"]:
                cards = soup.select(sel)
                if len(cards) > 1:
                    break

            log.info(f"  Eureka: {len(cards)} cards for '{query.replace('+', ' ')}'")

            for card in cards:
                try:
                    name_el = (card.select_one("a.product-item-link") or
                               card.select_one("strong.product-item-name") or
                               card.select_one("[class*='product-name']") or
                               card.select_one("h3 a") or
                               card.select_one("a[title]"))
                    if not name_el:
                        continue
                    name = (name_el.get_text(strip=True) or
                            name_el.get("title","")).strip()
                    if not name or not is_purifier(name):
                        continue

                    link_el  = card.select_one("a[href]")
                    link     = (urljoin("https://www.eurekaforbes.com",
                                        link_el["href"])
                                if link_el else url)

                    price_el  = (card.select_one("span.price") or
                                 card.select_one("[class*='price']"))
                    price_str = price_el.get_text(strip=True) if price_el else ""

                    mrp_el    = card.select_one(
                        "[class*='old-price'],[class*='regular-price']")
                    mrp_str   = mrp_el.get_text(strip=True) if mrp_el else ""

                    img_url = ""
                    img_el  = card.select_one("img")
                    if img_el:
                        img_url = best_img(img_el)
                        if img_url and img_url.startswith("/"):
                            img_url = "https://www.eurekaforbes.com" + img_url

                    price = extract_price(price_str)
                    mrp   = extract_price(mrp_str)

                    p = Product(
                        source       = "eureka_official",
                        brand        = "Eureka Forbes",
                        model        = name,
                        full_name    = name,
                        category     = extract_category(name),
                        storage_l    = extract_storage(name),
                        price_inr    = price,
                        mrp_inr      = mrp,
                        discount_pct = (round((mrp-price)/mrp*100,1)
                                        if mrp and price and mrp > price else None),
                        image_url    = img_url,
                        product_url  = link,
                    ).make_id()

                    if p.id in seen_ids:
                        continue

                    p.local_image = download_image(p.image_url, p.id)
                    products.append(p)
                    seen_ids.add(p.id)
                    log.info(f"    + {name[:55]}"
                             f"  img={'YES' if p.local_image else 'NO'}")

                except Exception:
                    log.debug(traceback.format_exc())

            time.sleep(random.uniform(2.0, 3.5))

    finally:
        driver.quit()

    log.info(f"  [Eureka Forbes/Aquaguard] Total: {len(products)}")
    return products
SOURCE_MAP = {
    "livpure": lambda s: scrape_shopify(SHOPIFY_SOURCES[0], s),
    "vguard":  lambda s: scrape_shopify(SHOPIFY_SOURCES[1], s),
    "faber":   lambda s: scrape_shopify(SHOPIFY_SOURCES[2], s),
    "kent":    scrape_kent,
    "lg":      scrape_lg,
    "eureka":  scrape_eureka,
}

def run_scrape(only_source=None):
    db       = DB()
    seen_ids = db.seen_ids()
    all_new  = []
    print("\n" + "="*50 + "\n  RO CATALOGUE V2 - SCRAPER\n" + "="*50)
    sources = ([only_source.lower()] if only_source
               else ["livpure","vguard","faber","kent","lg","eureka"])
    for src in sources:
        fn = SOURCE_MAP.get(src)
        if not fn:
            log.error(f"Unknown source: {src}")
            continue
        log.info(f"\n[SOURCE] {src.upper()}")
        try:
            prods = fn(seen_ids)
            for p in prods:
                db.insert(p)
            all_new.extend(prods)
            log.info(f"  -> {len(prods)} added from {src}")
        except Exception as e:
            log.error(f"  {src} FAILED: {e}\n{traceback.format_exc()}")
    db.close()
    print(f"\n  Total new this run: {len(all_new)}")
    print_status()

def print_status():
    db    = DB()
    total = db.count()
    rows  = db.all()
    db.close()
    print("\n" + "="*50 + "\n  CATALOGUE V2 STATUS\n" + "="*50)
    print(f"\n  Total: {total}")
    sources = Counter(r["source"] for r in rows)
    brands  = Counter(r["brand"]  for r in rows)
    imgs    = sum(1 for r in rows if r.get("local_image"))
    print("\n  By source:")
    for s, c in sources.most_common():
        print(f"    {s:<30} {c}")
    print("\n  By brand:")
    for b, c in brands.most_common():
        print(f"    {b:<25} {c:>3}  {'#'*c}")
    no_img = [r["full_name"] for r in rows if not r.get("local_image")]
    print(f"\n  With image : {imgs} / {total}")
    if no_img:
        print(f"  No image ({len(no_img)}):")
        for n in no_img[:10]:
            print(f"    {n[:65]}")
        if len(no_img) > 10:
            print(f"    ... and {len(no_img)-10} more")
    print(f"\n  DB    : {DB_PATH}")
    print(f"  Images: {IMAGE_DIR} ({len(list(IMAGE_DIR.glob('*.jpg')))} files)")

def run_export():
    import pandas as pd
    db   = DB()
    rows = db.all()
    db.close()
    if not rows:
        print("DB is empty.")
        return
    df = pd.DataFrame(rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(BASE_DIR / f"catalogue_v2_{ts}.csv", index=False)
    with pd.ExcelWriter(BASE_DIR / f"catalogue_v2_{ts}.xlsx", engine="openpyxl") as w:
        df.to_excel(w, sheet_name="All", index=False)
        for brand, grp in df.groupby("brand"):
            sheet = re.sub(r"[^\w\s]","",str(brand))[:31]
            grp.to_excel(w, sheet_name=sheet, index=False)
    print(f"Exported {len(df)} products -> {BASE_DIR}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RO Catalogue V2 Scraper")
    parser.add_argument("--scrape", action="store_true")
    parser.add_argument("--source", type=str, default=None,
                        help="livpure / vguard / faber / kent / lg / eureka")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    if args.scrape:
        run_scrape(only_source=args.source)
    elif args.status:
        print_status()
    elif args.export:
        run_export()
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python scraper_v2.py --scrape")
        print("  python scraper_v2.py --scrape --source kent")
        print("  python scraper_v2.py --scrape --source lg")
        print("  python scraper_v2.py --scrape --source eureka")
        print("  python scraper_v2.py --status")