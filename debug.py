# import sqlite3
# from pathlib import Path

# # Show what paths the DB thinks images are at
# conn = sqlite3.connect("ro_catalogue/catalogue.db")
# sample = conn.execute(
#     "SELECT local_image FROM products WHERE local_image IS NOT NULL AND local_image != '' LIMIT 10"
# ).fetchall()
# print("Sample local_image paths in DB:")
# for row in sample:
#     print(f"  {row[0]}")

# all_paths = conn.execute(
#     "SELECT local_image FROM products WHERE local_image IS NOT NULL AND local_image != ''"
# ).fetchall()
# existing = sum(1 for (p,) in all_paths if Path(p).exists())
# print(f"\nOf {len(all_paths)} paths in DB -> {existing} actually exist on disk")
# conn.close()

# # Search for jpg files from current directory
# print("\nSearching for jpg files under current directory...")
# try:
#     jpgs = list(Path(".").rglob("*.jpg"))
#     if jpgs:
#         print(f"Found {len(jpgs)} jpg(s):")
#         for j in jpgs[:10]:
#             print(f"  {j}")
#         if len(jpgs) > 10:
#             print(f"  ... and {len(jpgs)-10} more")
#     else:
#         print("No jpg files found anywhere under current directory")
# except Exception as e:
#     print(f"Search error: {e}")
"""
debug_round3.py
AO Smith: find product custom post type via WP REST API
Pureit: follow subcategory links, check for JS data
"""
import requests, json, re, time
from bs4 import BeautifulSoup

UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
HDR = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
       "Accept": "application/json", "Referer": "https://www.google.co.in/"}

# ── AO SMITH ──────────────────────────────────────────────────────────
print("=" * 60)
print("AO SMITH")
print("=" * 60)

s = requests.Session()
s.headers.update(HDR)

# 1. Discover all registered WP post types
print("\n1. WP post types:")
r = s.get("https://www.aosmithindia.com/wp-json/wp/v2/types", timeout=15)
print(f"   HTTP {r.status_code}")
if r.status_code == 200:
    types = r.json()
    for slug, info in types.items():
        print(f"   {slug:<25} rest_base={info.get('rest_base','')}")

# 2. Try product-related custom post types
print("\n2. Custom post type endpoints:")
for cpt in ["product","products","water-purifier","water_purifier",
            "purifier","ao-product"]:
    url = f"https://www.aosmithindia.com/wp-json/wp/v2/{cpt}?per_page=100"
    try:
        r  = s.get(url, timeout=10)
        ct = r.headers.get("Content-Type","")
        print(f"   /wp/v2/{cpt:<20} HTTP {r.status_code}  size={len(r.text)}")
        if r.status_code == 200 and len(r.text) > 200:
            data = r.json()
            if isinstance(data, list) and data:
                p0 = data[0]
                print(f"     -> {len(data)} items  keys={list(p0.keys())[:8]}")
                # Check for product-like fields
                for k in ["title","name","slug","link","acf","meta"]:
                    val = p0.get(k)
                    if val:
                        print(f"     -> {k}: {str(val)[:100]}")
    except Exception as e:
        print(f"   ERROR: {e}")
    time.sleep(0.3)

# 3. Check a product detail page directly (from the link we saw)
print("\n3. AO Smith product page:")
prod_url = "https://www.aosmithindia.com/product/water-purifier/ro/proplanet-p7/"
r    = s.get(prod_url, headers={**HDR, "Accept": "text/html"}, timeout=15)
soup = BeautifulSoup(r.text, "lxml")
print(f"   HTTP {r.status_code}  size: {len(r.text)}")
for sc in soup.select("script[type='application/ld+json']"):
    try:
        data = json.loads(sc.string or "")
        t    = data.get("@type","")
        print(f"   JSON-LD type={t}")
        if t == "Product":
            print(json.dumps(data, indent=2)[:800])
    except Exception:
        pass

# Check for price/image in page source
for pattern, label in [
    (r'"price"\s*:\s*"?([\d,]+)"?', "price"),
    (r'"regularPrice"\s*:\s*"?([\d,]+)"?', "regularPrice"),
    (r'class="price"[^>]*>([^<]+)<', "price span"),
]:
    m = re.search(pattern, r.text)
    if m:
        print(f"   {label}: {m.group(1)[:50]}")

# Check for product archive JSON
print("\n4. WP product archive pages:")
for url in [
    "https://www.aosmithindia.com/product-category/water-purifier/?format=json",
    "https://www.aosmithindia.com/product-category/water-purifier/?json=1",
]:
    r = s.get(url, timeout=10)
    print(f"   {url.split('aosmithindia.com')[1][:60]}  HTTP {r.status_code}  size={len(r.text)}")

# ── PUREIT ────────────────────────────────────────────────────────────
print("\n\n" + "=" * 60)
print("PUREIT - subcategory pages")
print("=" * 60)

s2 = requests.Session()
s2.headers.update({**HDR, "Accept": "text/html"})

for url in [
    "https://www.pureitwater.com/water-purifier/ro-water-purifier",
    "https://www.pureitwater.com/water-purifier/uv-water-purifier",
]:
    print(f"\nURL: {url}")
    r    = s2.get(url, timeout=20)
    html = r.text
    soup = BeautifulSoup(html, "lxml")
    print(f"Status: {r.status_code}  size: {len(html)}")

    # Platform
    for marker, label in [
        ("cdn.shopify.com","SHOPIFY"), ("wp-content","WORDPRESS"),
        ("__NEXT_DATA__","NEXT.JS"), ("_nuxt","NUXT"),
        ("ng-version","ANGULAR"),
    ]:
        if marker in html:
            print(f">> {label}")

    # JSON-LD
    for sc in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(sc.string or "")
            t    = data.get("@type","")
            print(f"  JSON-LD type={t}")
            if t == "ItemList":
                items = data.get("itemListElement",[])
                print(f"  >> {len(items)} items")
                if items: print(f"  >> first: {json.dumps(items[0])[:200]}")
        except Exception:
            pass

    # __NEXT_DATA__
    nxt = soup.find("script", id="__NEXT_DATA__")
    if nxt:
        try:
            data = json.loads(nxt.string or "")
            pp   = data.get("props",{}).get("pageProps",{})
            print(f"  __NEXT_DATA__ pageProps keys: {list(pp.keys())[:10]}")
            def find_lists(obj, path="", depth=0):
                if depth > 5: return
                if isinstance(obj, list) and len(obj) > 2:
                    first = obj[0] if obj else {}
                    if isinstance(first, dict) and any(
                            k in first for k in ["name","title","slug","sku","url"]):
                        print(f"    List '{path}': {len(obj)} items  keys={list(first.keys())[:6]}")
                        print(f"      {json.dumps(first)[:250]}")
                        return
                if isinstance(obj, dict):
                    for k,v in obj.items():
                        find_lists(v, f"{path}.{k}", depth+1)
                elif isinstance(obj, list):
                    for i,v in enumerate(obj[:3]):
                        find_lists(v, f"{path}[{i}]", depth+1)
            find_lists(pp)
        except Exception as e:
            print(f"  NEXT_DATA error: {e}")

    # Product cards
    for sel in ["div[class*='product']","li[class*='product']",
                "[class*='ProductCard']","[class*='product-card']",
                "[class*='ProductTile']","[class*='product-tile']",
                "[class*='ProductItem']","[class*='product-item']"]:
        found = soup.select(sel)
        if found:
            cls = " ".join(found[0].get("class",[]))
            print(f"  {sel:<40} {len(found)} -> '{cls[:55]}'")

    # Large scripts
    for sc in soup.find_all("script"):
        txt = sc.string or ""
        if len(txt) > 15000:
            print(f"  Script {len(txt)}b: {txt[:120].strip()}")

    # Any product links
    links = set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if re.search(r"/product|/purifier|/ro|/uv|/p/", h, re.I):
            if len(h) > 20:
                links.add(h)
    print(f"  Product links ({len(links)}):")
    for l in sorted(links)[:8]:
        print(f"    {l[:90]}")
    time.sleep(1)

print("\nDone.")