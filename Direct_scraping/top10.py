from google.cloud import vision
from google.cloud.vision_v1 import types
import io
from urllib.parse import urlparse

class ReverseImageSearch:
    def __init__(self):
        self.client = vision.ImageAnnotatorClient()
    
    def load_image(self, image_path: str) -> types.Image:
        """Load image"""
        print(f"📁 Loading: {image_path}")
        with io.open(image_path, 'rb') as f:
            content = f.read()
            print(f"   ✅ {len(content)} bytes")
        return types.Image(content=content)
    
    def detect_web(self, image_path: str):
        """Get web detection results"""
        print("\n🚀 Vision API...")
        image = self.load_image(image_path)
        response = self.client.web_detection(image=image)
        web_detection = response.web_detection
        
        print("✅ Response OK")
        
        # Debug stats
        pages_count = len(web_detection.pages_with_matching_images) if web_detection.pages_with_matching_images else 0
        print(f"📊 Pages found: {pages_count}")
        
        return web_detection
    
    def get_top_urls(self, image_path: str, top_n: int = 20):
        """Return TOP URLs (no marketplace filter)"""
        web_detection = self.detect_web(image_path)
        pages = web_detection.pages_with_matching_images or []
        
        print(f"\n🔗 TOP {min(top_n, len(pages))} URLS:")
        print("=" * 80)
        
        top_urls = []
        for i, page in enumerate(pages[:top_n], 1):
            url = page.url
            title = getattr(page, 'page_title', 'No title')
            domain = urlparse(url).netloc
            
            print(f"{i:2d}. {domain}")
            print(f"   📱 {title[:70]}")
            print(f"   🔗 {url}")
            print()
            
            top_urls.append({
                'rank': i,
                'url': url,
                'title': title,
                'domain': domain
            })
        
        if not pages:
            print("❌ No pages found")
            print("💡 Try: Clear product photo, popular item")
        
        return top_urls

def main():
    searcher = ReverseImageSearch()
    
    # Your image path
    image_path = r'Image\Screenshot 2026-02-28 185633.png'
    
    # Get top 20 URLs (no filtering)
    urls = searcher.get_top_urls(image_path, top_n=20)
    
    # Save results
    import json
    with open('top_urls.json', 'w') as f:
        json.dump(urls, f, indent=2)
    
    print("✅ Saved: top_urls.json")

if __name__ == '__main__':
    main()
