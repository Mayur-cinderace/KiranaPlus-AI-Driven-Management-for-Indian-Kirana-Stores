import easyocr
import cv2
import numpy as np
import re
import os
import logging
import google.generativeai as genai
from config import Config
from difflib import SequenceMatcher

# Global OCR reader
reader = None
easyocr_version = None
gemini_model = None

def init_ocr():
    """Initialize OCR and AI services"""
    global reader, easyocr_version, gemini_model
    
    # Initialize EasyOCR
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

    # Initialize Gemini API
    if Config.GEMINI_API_KEY:
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            # Updated model names - try these in order
            model_names = [
                'gemini-1.5-flash',  # Latest and fastest
                'gemini-1.5-pro',   # More capable
                'models/gemini-1.5-flash',  # With models/ prefix
                'models/gemini-1.5-pro'     # With models/ prefix
            ]
            
            gemini_model = None
            for model_name in model_names:
                try:
                    gemini_model = genai.GenerativeModel(model_name)
                    # Test the model with a simple prompt
                    test_response = gemini_model.generate_content("Test")
                    print(f"Gemini API initialized successfully with model: {model_name}")
                    break
                except Exception as model_error:
                    print(f"Failed to initialize {model_name}: {str(model_error)}")
                    continue
            
            if gemini_model is None:
                print("Failed to initialize any Gemini model. Using local fallback only.")
            else:
                print("Gemini API initialized for intelligent unit fallback")
                
        except Exception as e:
            logging.error(f"Failed to initialize Gemini API: {str(e)}")
            print(f"Gemini API initialization error: {str(e)}")
            gemini_model = None
    else:
        print("Warning: GEMINI_API_KEY not set. Using local fallback logic only.")

def get_ocr_reader():
    """Get the OCR reader instance"""
    return reader

def get_gemini_model():
    """Get the Gemini model instance"""
    return gemini_model

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
    """Get intelligent unit fallback using Gemini API or local logic"""
    # First try local intelligence (faster and free)
    local_unit = get_local_unit_fallback(item_name)
    
    # Use Gemini API for more intelligent fallback
    if gemini_model:
        try:
            prompt = f"""
            For the grocery item "{item_name}", what is the most appropriate unit of measurement?
            
            Choose from these options only: kg, g, ltr, ml, pc, bottle, packet
            
            Consider:
            - Common grocery store packaging
            - Typical purchase quantities
            - Standard measurement units
            
            Respond with only the unit abbreviation (e.g., "kg", "g", "ltr", "ml", "pc", "bottle", "packet").
            Do not include explanations.
            
            Item: {item_name}
            Unit:"""
            
            # Generate content with timeout and error handling
            response = gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Low temperature for consistent results
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=10  # We only need a short response
                )
            )
            
            if response.text:
                suggested_unit = response.text.strip().lower()
                
                # Validate the response
                valid_units = ['kg', 'g', 'ltr', 'ml', 'pc', 'bottle', 'packet']
                if suggested_unit in valid_units:
                    print(f"✓ Gemini suggested unit '{suggested_unit}' for item '{item_name}'")
                    return suggested_unit
                else:
                    print(f"⚠ Gemini returned invalid unit '{suggested_unit}', using local fallback '{local_unit}'")
                    return local_unit
            else:
                print(f"⚠ Gemini returned empty response, using local fallback '{local_unit}'")
                return local_unit
                
        except Exception as e:
            logging.warning(f"Gemini API error for item '{item_name}': {str(e)}")
            print(f"⚠ Gemini API error: {str(e)}, using local fallback '{local_unit}'")
            return local_unit
    else:
        print(f"Applied intelligent unit fallback: '{item_name}' -> '{local_unit}'")
    
    return local_unit

def get_local_unit_fallback(item_name):
    """Local intelligent unit fallback based on item categorization"""
    item_lower = item_name.lower()
    
    # Liquids - typically measured in liters or ml
    liquid_keywords = ['oil', 'milk', 'water', 'juice', 'vinegar', 'sauce', 'syrup', 
                      'honey', 'ghee', 'coconut oil', 'mustard oil', 'olive oil']
    if any(keyword in item_lower for keyword in liquid_keywords):
        # Large quantities in liters, small in ml
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

def test_gemini_connection():
    """Test Gemini API connection and available models"""
    if not Config.GEMINI_API_KEY:
        print("❌ No GEMINI_API_KEY found in environment")
        return False
    
    try:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        
        # List available models
        print("📋 Available Gemini models:")
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                print(f"  - {model.name}")
        
        # Test with the latest model
        test_model = genai.GenerativeModel('gemini-1.5-flash')
        response = test_model.generate_content("Hello, respond with just 'OK'")
        
        if response.text:
            print(f"✅ Gemini API test successful: {response.text.strip()}")
            return True
        else:
            print("❌ Gemini API test failed: Empty response")
            return False
            
    except Exception as e:
        print(f"❌ Gemini API test failed: {str(e)}")
        return False

def fuzzy_match_inventory_item(extracted_name, inventory_items, threshold=0.6):
    """Find the closest matching inventory item using fuzzy string matching"""
    def clean_text(text):
        """Clean text for better matching - remove punctuation, convert to lowercase"""
        text = text.lower()
        # Remove punctuation and extra spaces
        text = ''.join(char for char in text if char.isalnum() or char.isspace())
        return ' '.join(text.split())  # Normalize whitespace
    
    def calculate_similarity(str1, str2):
        """Calculate similarity between two strings using multiple methods"""
        clean_str1 = clean_text(str1)
        clean_str2 = clean_text(str2)
        
        # Method 1: SequenceMatcher for overall similarity
        seq_similarity = SequenceMatcher(None, clean_str1, clean_str2).ratio()
        
        # Method 2: Check for substring matches (partial matching)
        substring_bonus = 0
        if clean_str1 in clean_str2 or clean_str2 in clean_str1:
            substring_bonus = 0.2
        
        # Method 3: Word-level matching for multi-word items
        words1 = set(clean_str1.split())
        words2 = set(clean_str2.split())
        
        if words1 and words2:
            word_intersection = len(words1.intersection(words2))
            word_union = len(words1.union(words2))
            word_similarity = word_intersection / word_union if word_union > 0 else 0
            
            # Combine similarities with weights
            combined_similarity = (seq_similarity * 0.6) + (word_similarity * 0.4) + substring_bonus
        else:
            combined_similarity = seq_similarity + substring_bonus
        
        return min(combined_similarity, 1.0)  # Cap at 1.0
    
    if not inventory_items or not extracted_name:
        return None
    
    cleaned_extracted = clean_text(extracted_name)
    if not cleaned_extracted:
        return None
    
    best_match = None
    best_score = 0
    
    print(f"Fuzzy matching '{extracted_name}' against {len(inventory_items)} inventory items")
    
    for item in inventory_items:
        item_name = item.get('itemName', '')
        brand = item.get('brand', '')
        category = item.get('category', '')
        
        # Try matching against item name
        name_similarity = calculate_similarity(extracted_name, item_name)
        
        # Try matching against brand + item name combination
        brand_name_combo = f"{brand} {item_name}".strip()
        brand_similarity = calculate_similarity(extracted_name, brand_name_combo) if brand and brand != 'NA' else 0
        
        # Try matching against category + item name
        category_combo = f"{category} {item_name}".strip()
        category_similarity = calculate_similarity(extracted_name, category_combo) if category else 0
        
        # Take the best similarity score
        max_similarity = max(name_similarity, brand_similarity, category_similarity)
        
        if max_similarity > best_score and max_similarity >= threshold:
            best_score = max_similarity
            best_match = {
                'inventory_item': item,
                'similarity_score': max_similarity,
                'matched_field': 'name' if name_similarity == max_similarity else 
                                'brand_name' if brand_similarity == max_similarity else 'category_name',
                'extracted_name': extracted_name,
                'matched_name': item_name
            }
            print(f"  New best match: '{item_name}' (score: {max_similarity:.3f})")
    
    if best_match:
        print(f"✓ Best match for '{extracted_name}': '{best_match['matched_name']}' (score: {best_match['similarity_score']:.3f})")
    else:
        print(f"✗ No good match found for '{extracted_name}' (threshold: {threshold})")
    
    return best_match