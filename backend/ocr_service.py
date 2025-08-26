import easyocr
import cv2
import numpy as np
import re
import os
import logging
from config import Config

# Global OCR reader
reader = None
easyocr_version = None

def init_ocr():
    """Initialize EasyOCR"""
    global reader, easyocr_version
    
    try:
        print("Initializing EasyOCR (CPU mode)...")
        reader = easyocr.Reader(['en'], gpu=False)
        try:
            import pkg_resources
            easyocr_version = pkg_resources.get_distribution("easyocr").version
        except:
            easyocr_version = "unknown"
        print(f"EasyOCR initialized successfully! Version: {easyocr_version}")
    except Exception as e:
        logging.error(f"Failed to initialize EasyOCR: {str(e)}")
        print(f"ERROR: Failed to initialize EasyOCR: {str(e)}")
        reader = None

def get_ocr_reader():
    """Get the OCR reader instance"""
    return reader

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def preprocess_image(image_path):
    """Enhanced image preprocessing for better OCR results"""
    try:
        print(f"Preprocessing image: {image_path}")
        
        # Read image
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not read image file")
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray, h=30)
        
        # Apply adaptive thresholding for better text contrast
        thresh = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Optional: Apply morphological operations to clean up
        kernel = np.ones((2,2), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        # Save processed image
        processed_path = image_path.replace(".", "_processed.")
        cv2.imwrite(processed_path, cleaned)
        print(f"Preprocessed image saved to: {processed_path}")
        
        return processed_path
    except Exception as e:
        logging.error(f"Image preprocessing failed: {str(e)}")
        raise

def reconstruct_receipt_lines(ocr_results):
    """Reconstruct receipt lines from fragmented OCR results using bounding boxes"""
    # Sort by y-coordinate (top to bottom), then x-coordinate (left to right)
    sorted_results = sorted(ocr_results, key=lambda x: (x[0][0][1], x[0][0][0]))
    
    lines = []
    current_line = []
    current_y = None
    y_tolerance = 20  # pixels tolerance for same line
    
    for result in sorted_results:
        bbox, text, confidence = result
        # Get average y-coordinate of the text
        avg_y = (bbox[0][1] + bbox[2][1]) / 2
        
        if current_y is None or abs(avg_y - current_y) <= y_tolerance:
            # Same line
            current_line.append((text, confidence))
            current_y = avg_y if current_y is None else (current_y + avg_y) / 2
        else:
            # New line
            if current_line:
                # Join texts in current line
                combined_text = ' '.join([text for text, _ in current_line])
                avg_confidence = sum([conf for _, conf in current_line]) / len(current_line)
                lines.append((combined_text, avg_confidence))
            
            current_line = [(text, confidence)]
            current_y = avg_y
    
    # Don't forget the last line
    if current_line:
        combined_text = ' '.join([text for text, _ in current_line])
        avg_confidence = sum([conf for _, conf in current_line]) / len(current_line)
        lines.append((combined_text, avg_confidence))
    
    return lines

def get_intelligent_unit_fallback(item_name):
    """Get intelligent unit fallback using local logic"""
    return get_local_unit_fallback(item_name)

def get_local_unit_fallback(item_name):
    """Local intelligent unit fallback based on item categorization"""
    item_lower = item_name.lower()
    
    # Liquids - typically measured in liters or ml
    liquid_keywords = ['oil', 'milk', 'water', 'juice', 'vinegar', 'sauce', 'syrup', 
                      'honey', 'ghee', 'coconut oil', 'mustard oil', 'olive oil']
    if any(keyword in item_lower for keyword in liquid_keywords):
        if any(word in item_lower for word in ['bottle', 'can', 'pack', 'ltr', 'litre', 'liter']):
            return 'ltr'
        return 'ml'
    
    # Grains, flour, sugar - typically kg
    bulk_items = ['rice', 'wheat', 'flour', 'sugar', 'salt', 'dal', 'lentils', 
                  'quinoa', 'oats', 'semolina', 'besan', 'atta', 'maida']
    if any(keyword in item_lower for keyword in bulk_items):
        return 'kg'
    
    # Vegetables and fruits - typically kg
    produce_keywords = ['potato', 'onion', 'tomato', 'carrot', 'apple', 'banana', 
                       'orange', 'mango', 'grape', 'spinach', 'cabbage', 'cauliflower',
                       'brinjal', 'capsicum', 'beans', 'peas', 'okra', 'cucumber']
    if any(keyword in item_lower for keyword in produce_keywords):
        return 'kg'
    
    # Spices and small quantities - typically grams
    spice_keywords = ['masala', 'powder', 'spice', 'cumin', 'coriander', 'turmeric',
                     'chili', 'pepper', 'cardamom', 'cinnamon', 'cloves', 'garam masala']
    if any(keyword in item_lower for keyword in spice_keywords):
        return 'g'
    
    # Packaged items - typically pieces or packets
    packaged_keywords = ['biscuit', 'chocolate', 'candy', 'chips', 'noodles', 
                        'bread', 'cake', 'cookie', 'wafer']
    if any(keyword in item_lower for keyword in packaged_keywords):
        return 'packet'
    
    # Countable items - pieces
    countable_keywords = ['egg', 'apple', 'orange', 'banana', 'lemon', 'coconut',
                         'bottle', 'can', 'pack']
    if any(keyword in item_lower for keyword in countable_keywords):
        return 'pc'
    
    # Default fallback
    return 'pc'

def levenshtein_distance(s1, s2):
    """Compute the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def fuzzy_match_inventory_item(extracted_name, inventory_items):
    """Find the closest matching inventory item using Levenshtein distance with length penalty"""
    def clean_text(text):
        """Clean text for better matching - remove punctuation, convert to lowercase"""
        text = text.lower()
        text = ''.join(char for char in text if char.isalnum() or char.isspace())
        return ' '.join(text.split())  # Normalize whitespace
    
    if not inventory_items or not extracted_name:
        return None
    
    cleaned_extracted = clean_text(extracted_name)
    if not cleaned_extracted:
        return None
    
    best_match = None
    best_score = float('inf')  # Lower distance is better
    
    print(f"Matching '{extracted_name}' against {len(inventory_items)} inventory items")
    
    # Log all candidate matches for debugging
    candidate_matches = []
    
    for item in inventory_items:
        item_name = item.get('itemName', '')
        brand = item.get('brand', '')
        category = item.get('category', '')
        
        # Clean fields for comparison
        cleaned_item_name = clean_text(item_name)
        cleaned_brand_name = clean_text(f"{brand} {item_name}".strip()) if brand and brand != 'NA' else ''
        cleaned_category_name = clean_text(f"{category} {item_name}".strip()) if category else ''
        
        # Calculate Levenshtein distances
        name_distance = levenshtein_distance(cleaned_extracted, cleaned_item_name)
        brand_distance = levenshtein_distance(cleaned_extracted, cleaned_brand_name) if cleaned_brand_name else float('inf')
        category_distance = levenshtein_distance(cleaned_extracted, cleaned_category_name) if cleaned_category_name else float('inf')
        
        # Apply length penalty: penalize large length differences
        length_penalty = abs(len(cleaned_extracted) - len(cleaned_item_name)) * 0.5
        name_distance += length_penalty
        
        if cleaned_brand_name:
            brand_length_penalty = abs(len(cleaned_extracted) - len(cleaned_brand_name)) * 0.5
            brand_distance += brand_length_penalty
        if cleaned_category_name:
            category_length_penalty = abs(len(cleaned_extracted) - len(cleaned_category_name)) * 0.5
            category_distance += category_length_penalty
        
        # Take the minimum distance
        min_distance = min(name_distance, brand_distance, category_distance)
        
        # Calculate similarity for reporting
        max_len = max(len(cleaned_extracted), len(cleaned_item_name))
        similarity_score = 1 - ((min_distance - length_penalty) / max_len) if max_len > 0 else 0
        
        # Store candidate for debugging
        candidate_matches.append({
            'item_name': item_name,
            'distance': min_distance,
            'similarity': similarity_score,
            'matched_field': 'name' if min_distance == name_distance else \
                           'brand_name' if min_distance == brand_distance else 'category_name'
        })
        
        if min_distance < best_score:
            best_score = min_distance
            matched_field = 'name' if min_distance == name_distance else \
                           'brand_name' if min_distance == brand_distance else 'category_name'
            similarity_score = 1 - ((min_distance - length_penalty) / max_len) if max_len > 0 else 0
            best_match = {
                'inventory_item': item,
                'similarity_score': similarity_score,
                'matched_field': matched_field,
                'extracted_name': extracted_name,
                'matched_name': item_name
            }
            print(f"  New best match: '{item_name}' (distance: {min_distance:.2f}, similarity: {similarity_score:.3f})")
    
    # Log all candidates for debugging
    print(f"Candidates for '{extracted_name}':")
    for candidate in sorted(candidate_matches, key=lambda x: x['distance']):
        print(f"  - {candidate['item_name']} (distance: {candidate['distance']:.2f}, similarity: {candidate['similarity']:.3f}, field: {candidate['matched_field']})")
    
    if best_match and best_match['similarity_score'] >= 0.5:  # Minimum similarity threshold
        print(f"✓ Best match for '{extracted_name}': '{best_match['matched_name']}' (score: {best_match['similarity_score']:.3f})")
        return best_match
    else:
        print(f"✗ No good match found for '{extracted_name}' (best similarity: {best_match['similarity_score']:.3f})")
        return None