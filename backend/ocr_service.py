import cv2
import numpy as np
import re
import os
import logging
from paddleocr import PaddleOCR
from config import Config
import pkg_resources

# Global OCR reader
reader = None
paddleocr_version = None

def init_ocr():
    """Initialize PaddleOCR"""
    global reader, paddleocr_version
    
    try:
        print("Initializing PaddleOCR (CPU mode)...")
        reader = PaddleOCR(use_angle_cls=True, lang='en')
        try:
            paddleocr_version = pkg_resources.get_distribution("paddleocr").version
        except:
            paddleocr_version = "unknown"
        print(f"PaddleOCR initialized successfully! Version: {paddleocr_version}")
    except Exception as e:
        logging.error(f"Failed to initialize PaddleOCR: {str(e)}")
        print(f"ERROR: Failed to initialize PaddleOCR: {str(e)}")
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
        
        # Apply bilateral filter for edge-preserving denoising
        denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
        
        # Apply Otsu's thresholding for better contrast
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Save processed image, ensuring only one '_processed' suffix
        base, ext = os.path.splitext(image_path)
        if base.endswith('_processed'):
            processed_path = image_path
        else:
            processed_path = f"{base}_processed{ext}"
        cv2.imwrite(processed_path, thresh)
        print(f"Preprocessed image saved to: {processed_path}")
        
        return processed_path
    except Exception as e:
        logging.error(f"Image preprocessing failed: {str(e)}")
        raise

def reconstruct_receipt_lines(ocr_results):
    """Reconstruct receipt lines from OCR results using bounding boxes"""
    # Sort by y-coordinate (top to bottom), then x-coordinate (left to right)
    sorted_results = sorted(ocr_results, key=lambda x: (x[0][0][1], x[0][0][0]))
    
    lines = []
    current_line = []
    current_y = None
    y_tolerance = 30  # Adjusted for receipt line spacing
    
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
    """Find the closest matching inventory item using Levenshtein distance"""
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
        
        # Apply length penalty
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
        
        if min_distance < best_score:
            best_score = min_distance
            matched_field = 'name' if min_distance == name_distance else \
                           'brand_name' if min_distance == brand_distance else 'category_name'
            best_match = {
                'inventory_item': item,
                'similarity_score': similarity_score,
                'matched_field': matched_field,
                'extracted_name': extracted_name,
                'matched_name': item_name
            }
            print(f"  New best match: '{item_name}' (distance: {min_distance:.2f}, similarity: {similarity_score:.3f})")
    
    if best_match and best_match['similarity_score'] >= 0.5:  # Minimum similarity threshold
        print(f"✓ Best match for '{extracted_name}': '{best_match['matched_name']}' (score: {best_match['similarity_score']:.3f})")
        return best_match
    else:
        print(f"✗ No good match found for '{extracted_name}' (best similarity: {best_match['similarity_score']:.3f})")
        return None

def parse_ocr_results(results):
    """Parse PaddleOCR results handling different formats"""
    ocr_results = []
    
    print(f"Parsing OCR results. Type: {type(results)}")
    
    # Handle different PaddleOCR result formats
    if isinstance(results, list):
        for page_result in results:
            if page_result is None:
                continue
                
            # Handle PaddleX OCRResult objects
            if hasattr(page_result, '__class__') and 'OCRResult' in str(type(page_result)):
                print(f"Found OCRResult object: {type(page_result)}")
                try:
                    # Extract data from PaddleX OCRResult
                    if 'dt_polys' in page_result and 'rec_texts' in page_result and 'rec_scores' in page_result:
                        dt_polys = page_result['dt_polys']
                        rec_texts = page_result['rec_texts']
                        rec_scores = page_result['rec_scores']
                        
                        print(f"Found {len(rec_texts)} detected texts: {rec_texts}")
                        print(f"Found {len(rec_scores)} confidence scores: {rec_scores}")
                        print(f"Found {len(dt_polys)} bounding boxes")
                        
                        # Combine the data
                        for i in range(min(len(dt_polys), len(rec_texts), len(rec_scores))):
                            bbox = dt_polys[i]
                            text = rec_texts[i]
                            confidence = rec_scores[i]
                            
                            if text and text.strip():
                                # Convert numpy array to list for bbox if needed
                                if hasattr(bbox, 'tolist'):
                                    bbox = bbox.tolist()
                                
                                ocr_results.append((bbox, str(text).strip(), float(confidence)))
                                print(f"Added OCR result: '{text}' (confidence: {confidence:.3f})")
                    else:
                        print("Required keys not found in OCRResult")
                        
                except Exception as e:
                    print(f"Error parsing OCRResult: {str(e)}")
                    continue
                    
            # Handle standard list format
            elif isinstance(page_result, list):
                for item in page_result:
                    try:
                        # Handle different item formats
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            if len(item) == 2:
                                # Format: [bbox, (text, confidence)]
                                bbox, text_conf = item
                                if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                                    text, confidence = text_conf
                                else:
                                    text = str(text_conf)
                                    confidence = 1.0
                            elif len(item) == 3:
                                # Format: [bbox, text, confidence]
                                bbox, text, confidence = item
                            else:
                                continue
                                
                            # Validate and add result
                            if bbox and text and isinstance(confidence, (int, float)):
                                ocr_results.append((bbox, str(text).strip(), float(confidence)))
                                
                    except Exception as e:
                        print(f"Error parsing item {item}: {str(e)}")
                        continue
            else:
                print(f"Unexpected page result type: {type(page_result)}")
    
    print(f"Successfully parsed {len(ocr_results)} OCR results")
    return ocr_results