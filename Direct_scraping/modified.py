from google.cloud import vision
import io
import cv2
import numpy as np
import re
from urllib.parse import quote
import json

class ROIdentifier:
    """Complete pipeline for clicked RO purifier photos"""
    
    def __init__(self):
        self.client = vision.ImageAnnotatorClient()
        
        # Indian RO brands
        self.brands = [
            'kent', 'aquaguard', 'pureit', 'livpure', 'blue star',
            'havells', 'ao smith', 'eureka forbes', 'hindware',
            'tata swach', 'lg', 'voltas', 'whirlpool', 'mi', 'xiaomi'
        ]
    
    # ========== STEP 1: AUTO-CROP RO ==========
    def crop_ro_purifier(self, image_path):
        """Auto-detect and crop RO purifier from image"""
        print("🖼️  STEP 1: Auto-cropping RO purifier...")
        
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot load: {image_path}")
        
        h, w = img.shape[:2]
        print(f"   Original size: {w}x{h}")
        
        # Enhance contrast
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel = lab[:,:,0]
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        l_channel = clahe.apply(l_channel)
        lab[:,:,0] = l_channel
        img_enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Find edges
        gray = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter for RO-shaped rectangles
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 5000 < area < 500000:  # RO size
                x, y, w_cnt, h_cnt = cv2.boundingRect(cnt)
                aspect = w_cnt / float(h_cnt)
                if 0.5 < aspect < 3.5:  # Vertical or horizontal RO
                    candidates.append((x, y, w_cnt, h_cnt, area))
        
        if candidates:
            # Pick largest
            x, y, w_crop, h_crop, _ = max(candidates, key=lambda c: c[4])
            # Add 10% margin
            margin_w = int(w_crop * 0.1)
            margin_h = int(h_crop * 0.1)
            x = max(0, x - margin_w)
            y = max(0, y - margin_h)
            w_crop = min(w - x, w_crop + 2*margin_w)
            h_crop = min(h - y, h_crop + 2*margin_h)
            cropped = img[y:y+h_crop, x:x+w_crop]
            print(f"   ✅ Cropped to: {w_crop}x{h_crop}")
        else:
            # Fallback: center 70%
            print("   ⚠️  No RO detected, center crop")
            x = int(w * 0.15)
            y = int(h * 0.15)
            cropped = img[y:int(h*0.85), x:int(w*0.85)]
        
        # Save
        cropped_path = image_path.replace('.png', '_cropped.jpg').replace('.jpg', '_cropped.jpg')
        cv2.imwrite(cropped_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        print(f"   💾 Saved: {cropped_path}")
        
        return cropped_path
    
    # ========== STEP 2: OCR TEXT EXTRACTION ==========
    def extract_text(self, image_path):
        """Extract all text from RO image"""
        print("\n📝 STEP 2: OCR text extraction...")
        
        with io.open(image_path, 'rb') as f:
            image = vision.Image(content=f.read())
        
        response = self.client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            print("   ⚠️  No text detected")
            return ""
        
        full_text = texts[0].description
        print(f"   ✅ Extracted {len(full_text)} characters:")
        print("   " + "-" * 50)
        for line in full_text.split('\n')[:10]:  # First 10 lines
            print(f"   {line}")
        print("   " + "-" * 50)
        
        return full_text
    
    # ========== STEP 3: PARSE BRAND & MODEL ==========
    def parse_brand_model(self, ocr_text):
        """Extract brand and model from OCR text"""
        print("\n🔍 STEP 3: Parsing brand & model...")
        
        text_lower = ocr_text.lower()
        lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
        
        # Find brand
        brand = None
        brand_line_idx = -1
        for b in self.brands:
            for idx, line in enumerate(lines):
                if b in line.lower():
                    brand = b
                    brand_line_idx = idx
                    break
            if brand:
                break
        
        # Find model (look near brand or for model patterns)
        model = None
        model_keywords = ['grand', 'enhance', 'supreme', 'essential', 'ultra', 
                         'max', 'plus', 'pro', 'elite', 'prime']
        
        if brand_line_idx >= 0:
            # Check next 3 lines
            for idx in range(brand_line_idx, min(brand_line_idx + 4, len(lines))):
                line = lines[idx]
                # Model usually has keywords or alphanumeric codes
                if any(kw in line.lower() for kw in model_keywords):
                    model = line
                    break
                # Or model codes like "RO-7890"
                if re.search(r'[A-Z]{2,4}[-\s]?\d{3,5}', line, re.IGNORECASE):
                    model = line
                    break
        
        # Look for capacity (7L, 8L)
        capacity = None
        capacity_match = re.search(r'(\d+\.?\d*)\s*[lL]', ocr_text)
        if capacity_match:
            capacity = capacity_match.group(0)
        
        # Look for tech specs
        tech_specs = []
        if 'ro' in text_lower:
            tech_specs.append('RO')
        if 'uv' in text_lower:
            tech_specs.append('UV')
        if 'uf' in text_lower:
            tech_specs.append('UF')
        
        result = {
            'brand': brand.title() if brand else None,
            'model': model,
            'capacity': capacity,
            'tech': '+'.join(tech_specs) if tech_specs else None,
            'raw_text': ocr_text
        }
        
        print(f"   🏷️  Brand: {result['brand'] or 'Unknown'}")
        print(f"   📦 Model: {result['model'] or 'Unknown'}")
        print(f"   💧 Capacity: {result['capacity'] or 'Unknown'}")
        print(f"   ⚙️  Tech: {result['tech'] or 'Unknown'}")
        
        return result
    
    # ========== STEP 4: GENERATE SEARCH URLS ==========
    def generate_search_urls(self, parsed_data):
        """Generate marketplace search URLs from parsed data"""
        print("\n🔗 STEP 4: Generating search URLs...")
        
        brand = parsed_data['brand']
        model = parsed_data['model']
        
        # Build search query
        query_parts = []
        if brand:
            query_parts.append(brand)
        if model:
            query_parts.append(model)
        query_parts.append('RO water purifier')
        
        search_query = ' '.join(query_parts)
        encoded_query = quote(search_query)
        
        urls = {
            'amazon_in': f"https://www.amazon.in/s?k={encoded_query}",
            'flipkart': f"https://www.flipkart.com/search?q={encoded_query}",
            'snapdeal': f"https://www.snapdeal.com/search?keyword={encoded_query}",
            'urbancompany': f"https://www.urbancompany.com/search?q={encoded_query}",
            'google': f"https://www.google.com/search?q={encoded_query}+buy+online"
        }
        
        print(f"   🔍 Search query: {search_query}")
        print(f"   ✅ Generated {len(urls)} marketplace URLs")
        
        return urls
    
    # ========== STEP 5: VISION WEB DETECTION (FALLBACK) ==========
    def vision_web_detection(self, image_path):
        """Vision API web detection as fallback"""
        print("\n🌐 STEP 5: Vision API web detection (fallback)...")
        
        with io.open(image_path, 'rb') as f:
            image = vision.Image(content=f.read())
        
        response = self.client.web_detection(image=image)
        web = response.web_detection
        
        pages = web.pages_with_matching_images or []
        entities = web.web_entities or []
        
        print(f"   📊 Web entities: {len(entities)}")
        print(f"   🔗 Matching pages: {len(pages)}")
        
        # Get top entities
        top_entities = []
        for entity in entities[:5]:
            if entity.description:
                top_entities.append({
                    'description': entity.description,
                    'score': entity.score
                })
                print(f"      • {entity.description} ({entity.score:.2f})")
        
        # Get top pages
        top_pages = []
        for page in pages[:10]:
            top_pages.append({
                'url': page.url,
                'title': getattr(page, 'page_title', '')
            })
        
        return {
            'entities': top_entities,
            'pages': top_pages
        }
    
    # ========== MAIN PIPELINE ==========
    def identify_ro(self, image_path):
        """Complete identification pipeline"""
        print("="*60)
        print("🚀 RO PURIFIER IDENTIFICATION PIPELINE")
        print("="*60)
        
        results = {
            'input_image': image_path,
            'cropped_image': None,
            'ocr_text': None,
            'parsed_data': None,
            'search_urls': None,
            'vision_data': None
        }
        
        try:
            # Step 1: Crop
            cropped_path = self.crop_ro_purifier(image_path)
            results['cropped_image'] = cropped_path
            
            # Step 2: OCR
            ocr_text = self.extract_text(cropped_path)
            results['ocr_text'] = ocr_text
            
            # Step 3: Parse
            parsed = self.parse_brand_model(ocr_text)
            results['parsed_data'] = parsed
            
            # Step 4: Generate search URLs
            search_urls = self.generate_search_urls(parsed)
            results['search_urls'] = search_urls
            
            # Step 5: Vision fallback
            vision_data = self.vision_web_detection(cropped_path)
            results['vision_data'] = vision_data
            
            # Print summary
            self.print_summary(results)
            
            return results
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return results
    
    def print_summary(self, results):
        """Print final summary"""
        print("\n" + "="*60)
        print("📋 IDENTIFICATION RESULTS")
        print("="*60)
        
        parsed = results.get('parsed_data', {})
        if parsed and parsed.get('brand'):
            print(f"\n✅ IDENTIFIED:")
            print(f"   Brand: {parsed['brand']}")
            print(f"   Model: {parsed.get('model', 'Unknown')}")
            print(f"   Capacity: {parsed.get('capacity', 'Unknown')}")
            print(f"   Tech: {parsed.get('tech', 'Unknown')}")
        else:
            print("\n⚠️  Could not identify brand from text")
        
        print(f"\n🛒 SEARCH ON MARKETPLACES:")
        urls = results.get('search_urls', {})
        for name, url in urls.items():
            print(f"   {name.upper()}: {url}")
        
        vision = results.get('vision_data', {})
        if vision.get('pages'):
            print(f"\n🌐 VISION FOUND {len(vision['pages'])} MATCHING PAGES:")
            for i, page in enumerate(vision['pages'][:5], 1):
                print(f"   {i}. {page['url']}")
        else:
            print(f"\n💡 Vision found 0 pages (normal for clicked photos)")
        
        print("\n" + "="*60)

def main():
    # Initialize
    identifier = ROIdentifier()
    
    # Your clicked RO image
    image_path = r'Image/WhatsApp Image 2026-02-28 at 8.48.01 PM.jpeg'
    
    # Run complete pipeline
    results = identifier.identify_ro(image_path)
    
    # Save results
    output = {
        'brand': results['parsed_data']['brand'] if results['parsed_data'] else None,
        'model': results['parsed_data']['model'] if results['parsed_data'] else None,
        'search_urls': results['search_urls'],
        'vision_pages': [p['url'] for p in results['vision_data']['pages']] if results['vision_data'] else []
    }
    
    with open('ro_identification_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print("\n✅ Results saved to: ro_identification_results.json")
    print(f"✅ Cropped image: {results['cropped_image']}")

if __name__ == '__main__':
    main()
