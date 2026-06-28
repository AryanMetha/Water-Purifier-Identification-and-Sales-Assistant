import os
import requests
import re
from PIL import Image
from io import BytesIO
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.cloud import vision

# ===== CONFIG (just drop your image here) =====
LOCAL_IMAGE_PATH = "Screenshot 2026-02-28 114140.png"  # Your RO purifier photo
# ============================================

SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

def get_vision_client():
    """OAuth login (browser popup first time only)"""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if not os.path.exists('credentials.json'):
            raise FileNotFoundError(
                "Download credentials.json from:\n"
                "console.cloud.google.com/apis/credentials → CREATE CREDENTIALS → OAuth Desktop"
            )
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return vision.ImageAnnotatorClient(credentials=creds)

def resize_image(image_path: str, max_width: int = 1920, quality: int = 85) -> bytes:
    """RGBA fix + resize → optimized JPEG"""
    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        
        img.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

def google_vision_reverse_image(image_bytes: bytes, client):
    """Vision WEB_DETECTION = reverse image search"""
    image = vision.Image(content=image_bytes)
    response = client.web_detection(image=image)
    web_detection = response.web_detection
    
    return {
        "entities": [{"desc": e.description, "score": f"{e.score:.2f}"} 
                    for e in web_detection.web_entities or []],
        "pages": [{"url": p.url, "score": f"{p.score:.2f}"} 
                 for p in web_detection.pages_with_matching_images or []],
        "similar_images": [{"url": i.url} 
                          for i in web_detection.visually_similar_images or []]
    }

def filter_marketplaces(pages: list) -> list:
    """Amazon/Flipkart only"""
    domains = ["amazon.in", "amazon.com", "flipkart.com"]
    return [p for p in pages if any(d in p["url"].lower() for d in domains)][:3]

def extract_product_details(url: str) -> dict:
    """Scrape brand/model/price"""
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        html = resp.text.lower()
        
        brands = ["kent", "aquaguard", "pureit", "ao smith", "havells", "livpure"]
        brand = next((b.capitalize() for b in brands if b in html), "Unknown")
        
        model_match = re.search(r"(grand|ro|uv|uf|plus|star|prime)[\s\-]*(\d+l?)?", html, re.I)
        model = model_match.group(0).title() if model_match else "Unknown"
        
        price_match = re.search(r"₹?[\d,]+", resp.text)
        price = price_match.group(0) if price_match else "N/A"
        
        return {"brand": brand, "model": model, "price": price, "url": url[:80] + "..."}
    except Exception as e:
        return {"brand": "Error", "model": str(e), "price": "N/A", "url": url}

def main():
    print("🚀 RO Purifier Identifier (Google Vision)")
    print("=" * 50)
    
    if not os.path.exists(LOCAL_IMAGE_PATH):
        print(f"❌ Missing image: {LOCAL_IMAGE_PATH}")
        print("📸 Put your RO purifier photo there and rerun!")
        return
    
    # 1. Authenticate (browser first time only)
    print("🔐 Authenticating with Google...")
    client = get_vision_client()
    print("✅ Auth OK")
    
    # 2. Process image
    print(f"📐 Processing {LOCAL_IMAGE_PATH}...")
    image_bytes = resize_image(LOCAL_IMAGE_PATH)
    print(f"📦 Size: {len(image_bytes)/1024:.0f} KB")
    
    # 3. Vision reverse image search
    print("🔍 Google Vision web detection...")
    results = google_vision_reverse_image(image_bytes, client)
    
    # 4. Find marketplaces
    marketplaces = filter_marketplaces(results["pages"])
    print(f"\n🛒 Marketplaces found: {len(marketplaces)}")
    
    if marketplaces:
        print("\n📋 Top matches:")
        for i, page in enumerate(marketplaces, 1):
            print(f"  {i}. {page['url']} (conf: {page['score']})")
        
        # Analyze best match
        best_url = marketplaces[0]["url"]
        product = extract_product_details(best_url)
        
        print("\n🎯 IDENTIFIED:")
        print(f"   Brand: {product['brand']}")
        print(f"   Model: {product['model']}")
        print(f"   Price: ₹{product['price']}")
        print(f"   Link:  {product['url']}")
        
    else:
        print("\n❌ No Amazon/Flipkart found")
        print("Entities:", [e["desc"] for e in results["entities"][:3]])

if __name__ == "__main__":
    main()
