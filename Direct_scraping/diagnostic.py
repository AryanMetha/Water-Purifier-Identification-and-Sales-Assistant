from google.cloud import vision
import io
import cv2
import numpy as np
import re
from urllib.parse import quote  # Only this import needed
import json

class ROIdentifier:
    def __init__(self):
        self.client = vision.ImageAnnotatorClient()
        self.brands = [
            'kent', 'aquaguard', 'pureit', 'livpure', 'blue star',
            'havells', 'ao smith', 'eureka forbes', 'hindware',
            'tata swach', 'lg', 'voltas', 'whirlpool', 'mi', 'xiaomi'
        ]
    
    def crop_ro_purifier(self, image_path):
        print("🖼️  STEP 1: Auto-cropping RO...")
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot load: {image_path}")
        
        h, w = img.shape[:2]
        print(f"   Original: {w}x{h}")
        
        # Enhance contrast
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel = lab[:,:,0]
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        l_channel = clahe.apply(l_channel)
        lab[:,:,0] = l_channel
        img_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Edges
        gray = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Find RO rectangles
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 5000 < area < 500000:
                x, y, w_cnt, h_cnt = cv2.boundingRect(cnt)
                aspect = w_cnt / float(h_cnt)
                if 0.5 < aspect < 3.5:
                    candidates.append((x, y, w_cnt, h_cnt, area))
        
        if candidates:
            x, y, w_crop, h_crop, _ = max(candidates, key=lambda c: c[4])
            margin_w = int(w_crop * 0.1)
            margin_h = int(h_crop * 0.1)
            x = max(0, x - margin_w)
            y = max(0, y - margin_h)
            w_crop = min(w - x, w_crop + 2*margin_w)
            h_crop = min(h - y, h_crop + 2*margin_h)
            cropped = img[y:y+h_crop, x:x+w_crop]
            print(f"   ✅ Cropped: {w_crop}x{h_crop}")
        else:
            print("   ⚠️  Center crop")
            x, y = int(w * 0.15), int(h * 0.15)
            cropped = img[y:int(h*0.85), x:int(w*0.85)]
        
        cropped_path = image_path.replace('.png', '_cropped.jpg').replace('.jpg', '_cropped.jpg')
        cv2.imwrite(cropped_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        print(f"   💾 {cropped_path}")
        return cropped_path
    
    def extract_text(self, image_path):
        print("\n📝 STEP 2: OCR...")
        with io.open(image_path, 'rb') as f:
            image = vision.Image(content=f.read())
        response = self.client.text_detection(image=image)
        texts = response.text_annotations
        if not texts:
            print("   ⚠️  No text")
            return ""
        full_text = texts[0].description
        print(f"   ✅ {len(full_text)} chars")
        print("   " + full_text[:200] + "...")
        return full_text
    
    def parse_brand_model(self, ocr_text):
        print("\n🔍 STEP 3: Parse brand...")
        text_lower = ocr_text.lower()
        lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
        
        # Brand
        brand = None
        for b in self.brands:
            for idx, line in enumerate(lines):
                if b in line.lower():
                    brand = b.title()
                    break
            if brand:
                break
        
        # Model
        model = None
        model_words = ['grand', 'enhance', 'supreme', 'ultra', 'max', 'plus']
        for line in lines:
            if any(w in line.lower() for w in model_words):
                model = line
                break
        
        # Capacity
        capacity = re.search(r'(\d+\.?\d*)\s*[lL]', ocr_text)
        capacity = capacity.group(0) if capacity else None
        
        print(f"   Brand: {brand or 'Unknown'}")
        print(f"   Model: {model or 'Unknown'}")
        
        return {
            'brand': brand,
            'model': model,
            'capacity': capacity
        }
    
    def generate_search_urls(self, parsed):
        print("\n🔗 STEP 4: Search URLs...")
        parts = []
        if parsed['brand']:
            parts.append(parsed['brand'])
        if parsed['model']:
            parts.append(parsed['model'])
        parts.append('ro purifier')
        
        query = ' '.join(parts)
        encoded = quote(query)
        
        urls = {
            'amazon': f"https://www.amazon.in/s?k={encoded}",
            'flipkart': f"https://www.flipkart.com/search?q={encoded}",
            'snapdeal': f"https://www.snapdeal.com/search?keyword={encoded}"
        }
        
        print(f"   Query: {query}")
        return urls
    
    def identify_ro(self, image_path):
        print("="*50)
        print("RO PURIFIER IDENTIFIER")
        print("="*50)
        
        cropped = self.crop_ro_purifier(image_path)
        ocr_text = self.extract_text(cropped)
        parsed = self.parse_brand_model(ocr_text)
        urls = self.generate_search_urls(parsed)
        
        print("\n📋 SUMMARY:")
        print(f"Brand: {parsed['brand'] or 'Unknown'}")
        print(f"URLs: {len(urls)} generated")
        for name, url in urls.items():
            print(f"{name}: {url}")
        
        # Save
        results = {'brand': parsed['brand'], 'urls': urls}
        with open('ro_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        print("\n✅ ro_results.json saved!")
        
        return results

# Run
if __name__ == '__main__':
    identifier = ROIdentifier()
    identifier.identify_ro(r'Image\Screenshot 2026-02-28 185633.png')
