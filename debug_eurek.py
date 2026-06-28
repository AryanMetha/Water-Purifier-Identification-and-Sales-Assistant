# # # # # # """
# # # # # # debug_eureka.py
# # # # # # Tests multiple approaches to get Eureka Forbes products.
# # # # # # Run this and paste output.
# # # # # # """
# # # # # # import requests, json, time
# # # # # # from bs4 import BeautifulSoup

# # # # # # UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"

# # # # # # def hdrs(referer="https://www.eurekaforbes.com/"):
# # # # # #     return {
# # # # # #         "User-Agent": UA,
# # # # # #         "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
# # # # # #         "Accept-Language": "en-IN,en;q=0.9",
# # # # # #         "Referer": referer,
# # # # # #         "DNT": "1",
# # # # # #     }

# # # # # # s = requests.Session()
# # # # # # s.headers.update(hdrs())

# # # # # # # First visit homepage to get cookies
# # # # # # print("=== Warming up session with homepage ===")
# # # # # # r = s.get("https://www.eurekaforbes.com/", timeout=15)
# # # # # # print(f"Homepage: {r.status_code}  cookies: {list(s.cookies.keys())}")
# # # # # # time.sleep(2)

# # # # # # # ── Test 1: Search page directly ──────────────────────────────────
# # # # # # print("\n=== Test 1: Search page ===")
# # # # # # r = s.get("https://www.eurekaforbes.com/search?q=ro+water+purifier&type=product",
# # # # # #           timeout=15)
# # # # # # print(f"Status: {r.status_code}  size: {len(r.text)}")
# # # # # # soup = BeautifulSoup(r.text, "lxml")
# # # # # # for sel in ["div.product-item-info","li.item.product",
# # # # # #             "div[class*='product']","ol.products"]:
# # # # # #     found = soup.select(sel)
# # # # # #     if found:
# # # # # #         print(f"  {sel} -> {len(found)} matches")

# # # # # # # ── Test 2: Catalog category page directly ────────────────────────
# # # # # # print("\n=== Test 2: Category page ===")
# # # # # # r = s.get("https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier",
# # # # # #           timeout=15)
# # # # # # print(f"Status: {r.status_code}  size: {len(r.text)}")
# # # # # # soup = BeautifulSoup(r.text, "lxml")
# # # # # # for sel in ["div.product-item-info","li.item.product",
# # # # # #             "div[class*='product']","script[type='application/ld+json']"]:
# # # # # #     found = soup.select(sel)
# # # # # #     if found:
# # # # # #         print(f"  {sel} -> {len(found)} matches")

# # # # # # # Check for JSON-LD product data
# # # # # # print("  JSON-LD blocks:")
# # # # # # for sc in soup.select("script[type='application/ld+json']"):
# # # # # #     try:
# # # # # #         data = json.loads(sc.string)
# # # # # #         print(f"    type: {data.get('@type','')}  keys: {list(data.keys())[:5]}")
# # # # # #     except Exception:
# # # # # #         pass

# # # # # # # ── Test 3: API endpoint guesses ─────────────────────────────────
# # # # # # print("\n=== Test 3: API endpoints ===")
# # # # # # apis = [
# # # # # #     "https://www.eurekaforbes.com/api/products?category=water-purifiers",
# # # # # #     "https://www.eurekaforbes.com/rest/V1/products?searchCriteria[filter_groups][0][filters][0][field]=category_id&searchCriteria[filter_groups][0][filters][0][value]=water-purifiers",
# # # # # #     "https://www.eurekaforbes.com/graphql",
# # # # # # ]
# # # # # # for url in apis:
# # # # # #     try:
# # # # # #         r = s.get(url, timeout=10)
# # # # # #         print(f"  {url.split('/')[-1]}: HTTP {r.status_code}  size: {len(r.text)}")
# # # # # #         if r.status_code == 200 and len(r.text) > 100:
# # # # # #             print(f"    preview: {r.text[:200]}")
# # # # # #     except Exception as e:
# # # # # #         print(f"  {url}: ERROR {e}")

# # # # # # # ── Test 4: Sitemap product URLs ──────────────────────────────────
# # # # # # print("\n=== Test 4: Sitemap product URLs ===")
# # # # # # r = s.get("https://www.eurekaforbes.com/sitemap.xml", timeout=15)
# # # # # # print(f"Sitemap: {r.status_code}  size: {len(r.text)}")
# # # # # # if r.status_code == 200:
# # # # # #     soup = BeautifulSoup(r.text, "xml")
# # # # # #     locs = [loc.text for loc in soup.find_all("loc")
# # # # # #             if "/p/" in loc.text or
# # # # # #                ("/water-purifier" in loc.text and "/c/" not in loc.text)]
# # # # # #     print(f"  Found {len(locs)} product-like URLs")
# # # # # #     for l in locs[:10]:
# # # # # #         print(f"    {l}")

# # # # # # # ── Test 5: Try one product URL directly ─────────────────────────
# # # # # # print("\n=== Test 5: Direct product page ===")
# # # # # # r = s.get("https://www.eurekaforbes.com/aquaguard-sure-delight-nxt-ro-uv-mtds-water-purifier/p/WTRWTRPWRAQUA00000022",
# # # # # #           timeout=15)
# # # # # # print(f"Status: {r.status_code}  size: {len(r.text)}")
# # # # # # if r.status_code == 200:
# # # # # #     soup = BeautifulSoup(r.text, "lxml")
# # # # # #     h1 = soup.find("h1")
# # # # # #     price = soup.select_one("span.price")
# # # # # #     img   = soup.select_one("img.gallery-placeholder__image")
# # # # # #     print(f"  h1: {h1.get_text() if h1 else 'NOT FOUND'}")
# # # # # #     print(f"  price: {price.get_text() if price else 'NOT FOUND'}")
# # # # # #     print(f"  img: {img.get('src','NOT FOUND') if img else 'NOT FOUND'}")

# # # # # # print("\nDone.")
# # # # # """
# # # # # debug_eureka2.py - Extract and print the ItemList JSON-LD from Eureka Forbes
# # # # # """
# # # # # import requests, json
# # # # # from bs4 import BeautifulSoup

# # # # # UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
# # # # # s  = requests.Session()
# # # # # s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
# # # # #                   "Referer": "https://www.google.co.in/"})

# # # # # # Warm up
# # # # # s.get("https://www.eurekaforbes.com/", timeout=15)

# # # # # CATEGORY_URLS = [
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier",
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/uv-water-purifier",
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/stainless-steel-purifier",
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/slim-water-purifier",
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/copper-water-purifier",
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/hot-and-ambient-purifier",
# # # # #     "https://www.eurekaforbes.com/c/water-purifiers/alkaline-boost-water-purifier",
# # # # # ]

# # # # # for url in CATEGORY_URLS[:2]:  # Just first 2 to see structure
# # # # #     print(f"\n{'='*60}")
# # # # #     print(f"URL: {url}")
# # # # #     r    = s.get(url, timeout=20)
# # # # #     soup = BeautifulSoup(r.text, "lxml")

# # # # #     for sc in soup.select("script[type='application/ld+json']"):
# # # # #         try:
# # # # #             data = json.loads(sc.string)
# # # # #             if data.get("@type") == "ItemList":
# # # # #                 items = data.get("itemListElement", [])
# # # # #                 print(f"\nItemList found: {len(items)} items")
# # # # #                 print(f"Full structure of first item:")
# # # # #                 if items:
# # # # #                     print(json.dumps(items[0], indent=2))
# # # # #                 print(f"\nFirst 5 item names:")
# # # # #                 for it in items[:5]:
# # # # #                     # ItemList items can be nested differently
# # # # #                     print(json.dumps(it, indent=2)[:300])
# # # # #                     print("---")
# # # # #         except Exception as e:
# # # # #             print(f"JSON parse error: {e}")

# # # # # print("\nDone.")
# # # # """
# # # # debug_eureka_html.py
# # # # Looks inside the full 245KB HTML for hidden product data.
# # # # """
# # # # import requests, json, re, time
# # # # from bs4 import BeautifulSoup

# # # # UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
# # # # s  = requests.Session()
# # # # s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
# # # #                   "Referer": "https://www.google.co.in/"})
# # # # s.get("https://www.eurekaforbes.com/", timeout=15)
# # # # time.sleep(1)

# # # # URL  = "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier"
# # # # r    = s.get(URL, timeout=20)
# # # # html = r.text
# # # # soup = BeautifulSoup(html, "lxml")

# # # # print(f"Page size: {len(html)} bytes")

# # # # # ── 1. Count all /dp/ URLs in the raw HTML ───────────────────────────
# # # # dp_urls = list(set(re.findall(r'(?:href=|url["\s:]+)["\']?(/dp/[^"\'>\s]+)', html)))
# # # # print(f"\n1. /dp/ product URLs in raw HTML: {len(dp_urls)}")
# # # # for u in dp_urls[:10]:
# # # #     print(f"   {u}")

# # # # # ── 2. Look for window.* JS data blobs ───────────────────────────────
# # # # print("\n2. JS data blobs:")
# # # # for sc in soup.find_all("script"):
# # # #     txt = sc.string or ""
# # # #     for keyword in ["productList", "product_list", "items", "catalogData",
# # # #                     "initialData", "__APOLLO__", "window.Magento"]:
# # # #         if keyword in txt and len(txt) > 200:
# # # #             idx = txt.find(keyword)
# # # #             snippet = txt[max(0,idx-10):idx+200]
# # # #             print(f"   [{keyword}] ...{snippet[:150]}...")
# # # #             break

# # # # # ── 3. All script tags that have JSON-like content ───────────────────
# # # # print("\n3. Large script tags:")
# # # # for sc in soup.find_all("script"):
# # # #     txt = sc.string or ""
# # # #     if len(txt) > 500 and ('"url"' in txt or '"name"' in txt):
# # # #         print(f"   size={len(txt)}  preview: {txt[:120].strip()}")

# # # # # ── 4. Try XHR API endpoint that Eureka likely calls ─────────────────
# # # # print("\n4. Testing XHR API endpoints:")
# # # # xhr_headers = {
# # # #     "User-Agent": UA,
# # # #     "Accept": "application/json, text/javascript, */*; q=0.01",
# # # #     "X-Requested-With": "XMLHttpRequest",
# # # #     "Referer": URL,
# # # # }
# # # # apis = [
# # # #     "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier?isAjax=1",
# # # #     "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier?ajax=1",
# # # #     "https://www.eurekaforbes.com/catalog/category/view/id/water-purifiers",
# # # #     "https://www.eurekaforbes.com/rest/all/V1/products?searchCriteria[filter_groups][0][filters][0][field]=category_id&searchCriteria[filter_groups][0][filters][0][value]=ro-water-purifier&searchCriteria[pageSize]=100",
# # # #     "https://www.eurekaforbes.com/graphql",
# # # # ]
# # # # for api in apis:
# # # #     try:
# # # #         resp = s.get(api, headers=xhr_headers, timeout=10)
# # # #         ct   = resp.headers.get("Content-Type","")
# # # #         print(f"   {api.split('eurekaforbes.com')[1][:60]}")
# # # #         print(f"     -> HTTP {resp.status_code}  type={ct[:40]}  size={len(resp.text)}")
# # # #         if resp.status_code == 200 and "json" in ct:
# # # #             print(f"     preview: {resp.text[:200]}")
# # # #     except Exception as e:
# # # #         print(f"   ERROR: {e}")

# # # # # ── 5. Check if page has data-mage-init or x-magento-init blobs ──────
# # # # print("\n5. Magento init data:")
# # # # for sc in soup.find_all("script", attrs={"type": "text/x-magento-init"}):
# # # #     txt = sc.string or ""
# # # #     if "product" in txt.lower() and len(txt) > 100:
# # # #         print(f"   size={len(txt)}  preview: {txt[:300]}")

# # # # print("\nDone.")
# # # """
# # # debug_eureka_nextjs.py
# # # Extracts and explores the 152KB Next.js pageProps JSON blob.
# # # """
# # # import requests, json, re, time
# # # from bs4 import BeautifulSoup

# # # UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
# # # s  = requests.Session()
# # # s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
# # #                   "Referer": "https://www.google.co.in/"})
# # # s.get("https://www.eurekaforbes.com/", timeout=15)
# # # time.sleep(1)

# # # URL  = "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier"
# # # r    = s.get(URL, timeout=20)
# # # soup = BeautifulSoup(r.text, "lxml")

# # # # Find the 152KB script tag
# # # big_script = None
# # # for sc in soup.find_all("script"):
# # #     txt = sc.string or ""
# # #     if len(txt) > 100000 and "pageProps" in txt:
# # #         big_script = txt
# # #         print(f"Found pageProps blob: {len(txt)} bytes")
# # #         break

# # # if not big_script:
# # #     print("ERROR: pageProps blob not found")
# # #     exit()

# # # data = json.loads(big_script)

# # # # Navigate into pageProps.page to find product list component
# # # page_components = data["props"]["pageProps"]["page"]
# # # print(f"\nTop-level page components ({len(page_components)}):")
# # # for comp in page_components:
# # #     ctype = comp.get("__component","?")
# # #     keys  = [k for k in comp.keys() if k != "__component"]
# # #     print(f"  {ctype}  keys={keys[:8]}")

# # # # Find the PLP component
# # # plp = None
# # # for comp in page_components:
# # #     if "plp" in comp.get("__component","").lower():
# # #         plp = comp
# # #         break

# # # if plp:
# # #     print(f"\nPLP component keys: {list(plp.keys())}")
# # #     # Look for products array
# # #     def find_products(obj, depth=0, path=""):
# # #         if depth > 6:
# # #             return
# # #         if isinstance(obj, list) and len(obj) > 5:
# # #             # Check if items look like products
# # #             first = obj[0] if obj else {}
# # #             if isinstance(first, dict):
# # #                 fkeys = set(first.keys())
# # #                 if any(k in fkeys for k in ["name","title","url","sku","slug","productId"]):
# # #                     print(f"\n  PRODUCTS FOUND at {path} ({len(obj)} items):")
# # #                     print(f"    Keys: {list(first.keys())}")
# # #                     print(f"    First item: {json.dumps(first, indent=2)[:400]}")
# # #                     return
# # #         if isinstance(obj, dict):
# # #             for k, v in obj.items():
# # #                 find_products(v, depth+1, f"{path}.{k}")
# # #         elif isinstance(obj, list):
# # #             for i, v in enumerate(obj[:3]):
# # #                 find_products(v, depth+1, f"{path}[{i}]")

# # #     find_products(plp, path="plp")
# # # else:
# # #     print("\nNo PLP component found, searching all components...")
# # #     def find_products(obj, depth=0, path=""):
# # #         if depth > 8:
# # #             return
# # #         if isinstance(obj, list) and len(obj) > 5:
# # #             first = obj[0] if obj else {}
# # #             if isinstance(first, dict):
# # #                 fkeys = set(first.keys())
# # #                 if any(k in fkeys for k in ["name","title","url","sku","slug","productId","handle"]):
# # #                     print(f"\n  LIST at {path} ({len(obj)} items):")
# # #                     print(f"    Keys: {list(first.keys())}")
# # #                     print(f"    Sample: {json.dumps(first, indent=2)[:300]}")
# # #                     return
# # #         if isinstance(obj, dict):
# # #             for k, v in obj.items():
# # #                 find_products(v, depth+1, f"{path}.{k}")
# # #         elif isinstance(obj, list):
# # #             for i, v in enumerate(obj[:5]):
# # #                 find_products(v, depth+1, f"{path}[{i}]")

# # #     find_products(data["props"]["pageProps"], path="pageProps")

# # # print("\nDone.")
# # import requests, json, time
# # from bs4 import BeautifulSoup

# # UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
# # s  = requests.Session()
# # s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
# # s.get("https://www.eurekaforbes.com/", timeout=15)
# # time.sleep(1)

# # URL  = "https://www.eurekaforbes.com/c/water-purifiers/ro-water-purifier"
# # soup = BeautifulSoup(s.get(URL, timeout=20).text, "lxml")

# # for sc in soup.find_all("script"):
# #     txt = sc.string or ""
# #     if len(txt) > 100000 and "pageProps" in txt:
# #         data       = json.loads(txt)
# #         components = data["props"]["pageProps"]["page"]

# #         for comp in components:
# #             if "trending" in comp.get("__component",""):
# #                 prods = comp["products"]
# #                 print(f"products type : {type(prods)}")
# #                 print(f"products value: {json.dumps(prods, indent=2)[:1000]}")

# #                 # Also dump entire component (truncated)
# #                 print(f"\nFull component (first 3000 chars):")
# #                 print(json.dumps(comp, indent=2)[:3000])
# #         break

# # print("\nDone.")
# """
# debug_eureka_strapi.py
# Tests Strapi API endpoints and extracts full product data from pageProps.
# """
# import requests, json, time, re
# from bs4 import BeautifulSoup

# UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
# s  = requests.Session()
# s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
#                   "Referer": "https://www.google.co.in/"})
# s.get("https://www.eurekaforbes.com/", timeout=15)
# time.sleep(1)

# BASE = "https://www.eurekaforbes.com"

# # ── 1. Try Strapi API endpoints ───────────────────────────────────────
# print("=== Strapi API attempts ===")
# strapi_urls = [
#     f"{BASE}/api/products?populate=*&pagination[pageSize]=100",
#     f"{BASE}/api/products?populate[media][fields][0]=url&populate[media][fields][1]=formats&pagination[pageSize]=100&filters[category][slug][$eq]=water-purifiers",
#     f"{BASE}/api/products?pagination[pageSize]=100&populate=media",
#     f"{BASE}/cms/api/products?populate=*&pagination[pageSize]=100",
#     f"{BASE}/api/categories/water-purifiers/products?populate=*",
# ]
# for url in strapi_urls:
#     try:
#         r  = s.get(url, timeout=10,
#                    headers={"Accept": "application/json"})
#         ct = r.headers.get("Content-Type","")
#         print(f"\n  {url.split(BASE)[1][:70]}")
#         print(f"  -> HTTP {r.status_code}  type={ct[:40]}  size={len(r.text)}")
#         if r.status_code == 200 and "json" in ct:
#             d = r.json()
#             print(f"  -> keys: {list(d.keys())[:6]}")
#             if "data" in d:
#                 print(f"  -> data count: {len(d['data'])}")
#                 print(f"  -> first item: {json.dumps(d['data'][0], indent=2)[:400]}")
#     except Exception as e:
#         print(f"  ERROR: {e}")

# # ── 2. Extract ALL products from pageProps across all category pages ──
# print("\n\n=== Extract from pageProps (all categories) ===")

# CATEGORY_URLS = [
#     "/c/water-purifiers/ro-water-purifier",
#     "/c/water-purifiers/uv-water-purifier",
#     "/c/water-purifiers/copper-water-purifier",
#     "/c/water-purifiers/stainless-steel-purifier",
#     "/c/water-purifiers/slim-water-purifier",
#     "/c/water-purifiers/hot-and-ambient-purifier",
#     "/c/water-purifiers/alkaline-boost-water-purifier",
# ]

# def extract_strapi_products(html):
#     """Pull all product records from the Next.js pageProps blob."""
#     soup  = BeautifulSoup(html, "lxml")
#     prods = []
#     for sc in soup.find_all("script"):
#         txt = sc.string or ""
#         if len(txt) > 50000 and "pageProps" in txt:
#             try:
#                 data       = json.loads(txt)
#                 components = data["props"]["pageProps"]["page"]
#                 for comp in components:
#                     # Check every component for a products.data list
#                     for key in comp:
#                         val = comp[key]
#                         if (isinstance(val, dict) and
#                                 "data" in val and
#                                 isinstance(val["data"], list)):
#                             for item in val["data"]:
#                                 if (isinstance(item, dict) and
#                                         "attributes" in item):
#                                     prods.append(item["attributes"])
#             except Exception as e:
#                 print(f"  parse error: {e}")
#             break
#     return prods

# all_products = {}  # materialId -> attributes dict
# for cat in CATEGORY_URLS:
#     url = BASE + cat
#     r   = s.get(url, timeout=20)
#     ps  = extract_strapi_products(r.text)
#     new = 0
#     for p in ps:
#         mid = p.get("materialId","")
#         if mid and mid not in all_products:
#             all_products[mid] = p
#             new += 1
#     print(f"  {cat.split('/')[-1]:<35} {len(ps):>3} in blob  "
#           f"{new:>3} new  total={len(all_products)}")
#     time.sleep(1)

# print(f"\nTotal unique products across all categories: {len(all_products)}")

# # Show what fields we have
# if all_products:
#     sample = next(iter(all_products.values()))
#     print(f"\nAvailable fields: {list(sample.keys())}")

#     # Show image URL structure
#     media = sample.get("media",{})
#     if isinstance(media, dict) and "data" in media:
#         mdata = media["data"]
#         if mdata:
#             fmt = mdata[0].get("attributes",{}).get("formats",{})
#             print(f"\nImage formats available: {list(fmt.keys())}")
#             for fname, fdata in fmt.items():
#                 print(f"  {fname}: {fdata.get('url','')[:80]}")

#     # Show price-related fields
#     price_fields = [k for k in sample.keys()
#                     if any(w in k.lower() for w in
#                            ["price","mrp","cost","rate","amount","commission"])]
#     print(f"\nPrice-related fields: {price_fields}")
#     for f in price_fields:
#         print(f"  {f}: {sample.get(f)}")

#     # Show 5 sample products
#     print(f"\nSample products:")
#     for mid, attrs in list(all_products.items())[:5]:
#         name     = attrs.get("plainName","")
#         slug     = attrs.get("slug","")
#         prod_url = f"{BASE}/dp/{mid}/{slug}"
#         media    = attrs.get("media",{})
#         img_url  = ""
#         if isinstance(media, dict) and "data" in media and media["data"]:
#             fmts = media["data"][0].get("attributes",{}).get("formats",{})
#             img_url = (fmts.get("large",{}).get("url","") or
#                        fmts.get("medium",{}).get("url","") or
#                        media["data"][0].get("attributes",{}).get("url",""))
#         print(f"  {name[:55]}")
#         print(f"    url: {prod_url}")
#         print(f"    img: {img_url[:70]}")

# print("\nDone.")
"""
Check what's in a single Eureka product page's pageProps blob.
Tells us if price + full image URL are available without extra scraping.
"""
import requests, json, time
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
s  = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
s.get("https://www.eurekaforbes.com/", timeout=15)
time.sleep(1)

URL = ("https://www.eurekaforbes.com/dp/GWPDDLTSR00000/"
       "aquaguard-sure-delight-nxt-ro-uv-uf-aquasaver-water-purifier")

r    = s.get(URL, timeout=20)
print(f"Status: {r.status_code}  size: {len(r.text)}")
soup = BeautifulSoup(r.text, "lxml")

# Find pageProps blob
for sc in soup.find_all("script"):
    txt = sc.string or ""
    if len(txt) > 10000 and "pageProps" in txt:
        print(f"Found script blob: {len(txt)} bytes")
        data = json.loads(txt)
        pp   = data["props"]["pageProps"]
        print(f"pageProps keys: {list(pp.keys())}")

        # Print full pageProps (truncated) to see structure
        print(f"\nFull pageProps (first 4000 chars):")
        print(json.dumps(pp, indent=2)[:4000])
        break

# Also check JSON-LD on product page
print("\n\nJSON-LD blocks on product page:")
for sc in soup.select("script[type='application/ld+json']"):
    try:
        data = json.loads(sc.string or "")
        t    = data.get("@type","")
        print(f"\n  type={t}  keys={list(data.keys())}")
        if t == "Product":
            print(json.dumps(data, indent=2)[:1500])
    except Exception:
        pass

print("\nDone.")