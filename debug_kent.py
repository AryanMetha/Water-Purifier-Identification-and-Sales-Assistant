"""
debug_scrapers.py
Run this to get exact class names and structure for Kent and LG.
Paste the output so scrapers can be fixed precisely.

Usage: python debug_scrapers.py
"""

import requests, time
from bs4 import BeautifulSoup
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
           "Referer": "https://www.google.co.in/"}

# =====================================================================
#  KENT
# =====================================================================
print("\n" + "="*60)
print("KENT DEBUG")
print("="*60)

try:
    resp = requests.get("https://www.kent.co.in/water-purifiers/ro/",
                        headers=HEADERS, timeout=20)
    print(f"Status: {resp.status_code}  |  Page size: {len(resp.text)} bytes")
    soup = BeautifulSoup(resp.text, "lxml")

    # Show all div classes containing 'product'
    divs = soup.select("div[class*='product']")
    print(f"\nAll div[class*='product'] ({len(divs)} found):")
    seen_classes = set()
    for d in divs:
        cls = " ".join(d.get("class", []))
        if cls not in seen_classes:
            seen_classes.add(cls)
            txt  = d.get_text(strip=True)[:80]
            link = d.find("a")
            print(f"\n  class: {cls}")
            print(f"  text : {txt}")
            if link:
                print(f"  href : {link.get('href','')[:80]}")

    # Also check what's in the main content area
    print("\n\nAll unique list item classes on page:")
    seen = set()
    for li in soup.find_all("li"):
        cls = " ".join(li.get("class", []))
        if cls and cls not in seen:
            seen.add(cls)
            print(f"  <li class='{cls}'>")

    # Check for any product names we recognize
    print("\n\nSearching for 'Kent' text in links:")
    for a in soup.find_all("a", href=True):
        txt = a.get_text(strip=True)
        if "kent" in a["href"].lower() and txt:
            print(f"  {txt[:60]}  ->  {a['href'][:80]}")

except Exception as e:
    print(f"Kent request failed: {e}")

# =====================================================================
#  LG  (Selenium)
# =====================================================================
print("\n\n" + "="*60)
print("LG DEBUG")
print("="*60)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-agent={UA}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    # Find Chrome
    for path in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\aryan\AppData\Local\Google\Chrome\Application\chrome.exe",
    ]:
        if Path(path).exists():
            opts.binary_location = path
            print(f"Chrome found at: {path}")
            break
    else:
        print("WARNING: Chrome not found in standard locations")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts)

    url = "https://www.lg.com/in/water-purifiers/?ec_model_status_code=Active"
    print(f"\nLoading: {url}")
    driver.get(url)

    # Wait for cards
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "li.c-product-list__item")))
        print("Cards loaded successfully")
    except Exception:
        print("Wait timed out - parsing anyway")

    # Scroll to load all
    for _ in range(5):
        driver.execute_script("window.scrollBy(0, window.innerHeight)")
        time.sleep(1)

    soup  = BeautifulSoup(driver.page_source, "lxml")
    cards = soup.select("li.c-product-list__item")
    print(f"\nFound {len(cards)} li.c-product-list__item cards")

    print("\n--- FIRST 3 CARDS - FULL STRUCTURE ---")
    for i, card in enumerate(cards[:3]):
        print(f"\n{'='*40}")
        print(f"CARD {i+1}")
        print(f"{'='*40}")
        # Print every tag with class and text/src
        for tag in card.find_all(True):
            cls  = tag.get("class","")
            txt  = tag.get_text(strip=True)[:70]
            src  = (tag.get("src","") or tag.get("data-src","") or
                    tag.get("data-lazy",""))[:80]
            href = tag.get("href","")[:80]
            if cls:
                print(f"  <{tag.name} class={cls}>")
                if txt:
                    print(f"    text: {txt}")
                if src:
                    print(f"    src : {src}")
                if href:
                    print(f"    href: {href}")

    driver.quit()

except ImportError:
    print("Selenium not installed")
except Exception as e:
    import traceback
    print(f"LG Selenium error: {e}")
    traceback.print_exc()

print("\n\nDone - paste the above output.")