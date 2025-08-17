from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import logging
import re
from datetime import datetime
from ocr_service import get_ocr_reader, allowed_file, preprocess_image, reconstruct_receipt_lines, fuzzy_match_inventory_item, get_intelligent_unit_fallback
from config import Config
from utils import get_inventory_items_from_db

ocr_bp = Blueprint('ocr', __name__)

def extract_items_from_text(texts_with_confidence):
    """Enhanced version of extract_items_from_text with fuzzy inventory matching"""
    items = []
    valid_units = ['kg', 'g', 'pc', 'pcs', 'gram', 'grams', 'piece', 'pieces', 
                   'ltr', 'litre', 'liter', 'ml', 'c', 'cup', 'cups', 'bottle', 'bottles',
                   'k6', 'k0', 'gu']
    
    # Unit mapping for OCR errors
    unit_mapping = {
        'gm': 'g', 'gms': 'g', 'kgs': 'kg', 'k6': 'kg', 'k0': 'kg', 'gu': 'g',
        'l': 'ltr', 'liters': 'ltr', 'litres': 'ltr', 'pcs': 'pc', 'pieces': 'pc'
    }
    
    # Load inventory items for fuzzy matching
    inventory_items = get_inventory_items_from_db()
    
    for text, confidence in texts_with_confidence:
        if confidence < 0.25:
            continue
            
        try:
            original_line = text
            line = text.lower().strip()
            
            if len(line) < 2:
                continue
            
            # Fix common OCR errors
            line = re.sub(r'[<>]', '', line)
            line = re.sub(r':', '', line)
            line = re.sub(r'[*/×\-–]', ' x ', line)
            line = re.sub(r'[^a-z0-9\s.x]', '', line)
            line = re.sub(r'\b(\d+)k\b(?![0-9])', lambda m: str(int(m.group(1)) * 1000), line)
            line = re.sub(r'\s+', ' ', line).strip()
            
            print(f"Processing line: '{original_line}' -> '{line}' (confidence: {confidence:.2f})")
            
            # Enhanced pattern matching
            patterns = [
                r'^([a-z\s]+?)\s+x\s+([\d.]+)\s+([a-z0-9]+)$',     # item x quantity unit
                r'^([a-z\s]+?)\s+x\s+([\d.]+)$',                    # item x quantity
                r'^([a-z\s]+?)\s+([\d.]+)\s+([a-z0-9]+)$',         # item quantity unit
                r'^([a-z\s]+?)\s+([\d.]+)$',                        # item quantity
                r'^([a-z]+)\s+x\s+([\d.]+)\s+([a-z0-9]+)$',        # single word item
                r'^([a-z\s]+)$',                                     # just item name
            ]
            
            matched = False
            for i, pattern in enumerate(patterns):
                match = re.match(pattern, line)
                if match:
                    name_part = match.group(1).strip()
                    quantity_part = match.group(2).strip() if len(match.groups()) > 1 else '1'
                    unit_part = match.group(3).strip() if len(match.groups()) > 2 and match.group(3) else ''
                    
                    # Validate name
                    if not re.search(r'[a-z]', name_part) or len(name_part) < 2:
                        continue
                    
                    # Process quantity
                    try:
                        quantity = float(quantity_part) if '.' in quantity_part else int(quantity_part)
                        if quantity <= 0 or quantity > 10000:
                            continue
                    except ValueError:
                        quantity = 1
                    
                    # FUZZY MATCHING: Try to match against inventory
                    fuzzy_match = fuzzy_match_inventory_item(name_part, inventory_items, threshold=0.6)
                    
                    if fuzzy_match:
                        # Use the matched inventory item details
                        inventory_item = fuzzy_match['inventory_item']
                        final_name = inventory_item['itemName']
                        
                        # Use inventory unit if available, otherwise fall back to extracted/intelligent unit
                        inventory_unit = inventory_item.get('unitSize', '').lower()
                        if inventory_unit and inventory_unit in valid_units:
                            final_unit = inventory_unit
                        elif unit_part:
                            final_unit = unit_mapping.get(unit_part, unit_part)
                        else:
                            final_unit = get_intelligent_unit_fallback(final_name)
                        
                        item = {
                            "item": final_name,
                            "quantity": quantity,
                            "unit": final_unit,
                            "confidence": round(confidence, 2),
                            "fuzzy_match": {
                                "similarity_score": round(fuzzy_match['similarity_score'], 3),
                                "original_extracted": name_part,
                                "matched_field": fuzzy_match['matched_field'],
                                "inventory_id": str(inventory_item.get('_id', '')),
                                "item_id": inventory_item.get('itemId', ''),
                                "selling_price": inventory_item.get('sellingPrice'),
                                "mrp": inventory_item.get('mrp')
                            }
                        }
                        
                        print(f"✓ Added fuzzy matched item: {final_name} (similarity: {fuzzy_match['similarity_score']:.3f})")
                        
                    else:
                        # No fuzzy match found, use original logic
                        if unit_part in unit_mapping:
                            unit_part = unit_mapping[unit_part]
                        elif not unit_part or unit_part not in valid_units:
                            intelligent_unit = get_intelligent_unit_fallback(name_part)
                            unit_part = intelligent_unit
                            print(f"Applied intelligent unit fallback: '{name_part}' -> '{intelligent_unit}'")
                        
                        item = {
                            "item": name_part.title(),
                            "quantity": quantity,
                            "unit": unit_part if unit_part else None,
                            "confidence": round(confidence, 2),
                            "fuzzy_match": None  # No match found
                        }
                        
                        print(f"✓ Added non-matched item: {name_part.title()}")
                    
                    items.append(item)
                    matched = True
                    break
            
            if not matched:
                print(f"✗ Line skipped (no pattern match): '{line}'")
                
        except Exception as e:
            logging.warning(f"Error processing line '{text}': {str(e)}")
            continue
    
    return items

@ocr_bp.route('/upload-receipt', methods=['POST'])
def upload_receipt():
    """Upload and process receipt image using OCR"""
    try:
        # Check if EasyOCR is initialized
        reader = get_ocr_reader()
        if reader is None:
            logging.error("EasyOCR not initialized")
            return jsonify({'error': 'OCR service not available'}), 500

        if 'receipt' not in request.files:
            logging.error("No file part in request")
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['receipt']
        if file.filename == '':
            logging.error("No file selected")
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            logging.error(f"Invalid file type: {file.filename}")
            return jsonify({'error': f'Invalid file type. Allowed: {", ".join(Config.ALLOWED_EXTENSIONS).upper()}'}), 400

        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        if file_size > Config.MAX_FILE_SIZE:
            logging.error(f"File too large: {file_size} bytes")
            return jsonify({'error': 'File too large. Maximum size is 5MB'}), 400
        file.seek(0)  # Reset file pointer

        # Save the uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        
        try:
            file.save(temp_path)
            print(f"File saved to: {temp_path}")
        except Exception as e:
            logging.error(f"Failed to save file {filename}: {str(e)}")
            return jsonify({'error': 'Failed to save uploaded file'}), 500

        # Process the image
        try:
            processed_path = preprocess_image(temp_path)
        except Exception as e:
            logging.error(f"Image processing failed for {filename}: {str(e)}")
            return jsonify({'error': 'Failed to process image'}), 500

        # Extract text using EasyOCR
        try:
            print("Extracting text with EasyOCR...")
            # Use detail=1 to get bounding boxes and confidence scores
            results = reader.readtext(processed_path, detail=1, paragraph=False)
            print(f"OCR completed. Found {len(results)} text elements.")
            
            # First, try to reconstruct lines from fragmented text
            reconstructed_lines = reconstruct_receipt_lines(results)
            print(f"Reconstructed into {len(reconstructed_lines)} lines:")
            for line, conf in reconstructed_lines:
                print(f"  Line: '{line}' (confidence: {conf:.2f})")
            
            # Also keep individual fragments as backup
            individual_fragments = [(result[1], result[2]) for result in results]
            print("Individual fragments:", [(text, f"{conf:.2f}") for text, conf in individual_fragments])
            
        except Exception as e:
            logging.error(f"EasyOCR failed for {processed_path}: {str(e)}")
            return jsonify({'error': 'Text extraction failed'}), 500

        # Extract items from reconstructed lines first, then from fragments
        print("\n=== Processing reconstructed lines ===")
        items_from_lines = extract_items_from_text(reconstructed_lines)
        
        print("\n=== Processing individual fragments ===")
        items_from_fragments = extract_items_from_text(individual_fragments)
        
        # Combine results, prioritizing reconstructed lines
        all_items = items_from_lines + items_from_fragments
        
        # Remove duplicates (simple name-based deduplication)
        seen_items = set()
        unique_items = []
        for item in all_items:
            item_key = item['item'].lower()
            if item_key not in seen_items:
                seen_items.add(item_key)
                unique_items.append(item)
        
        items = unique_items

        # Clean up temporary files
        try:
            os.remove(temp_path)
            if os.path.exists(processed_path):
                os.remove(processed_path)
            print("Temporary files cleaned up")
        except Exception as e:
            logging.error(f"Failed to clean up files for {filename}: {str(e)}")

        print(f"Successfully processed receipt. Found {len(items)} items.")
        return jsonify({
            'items': items,
            'total_items': len(items),
            'reconstructed_lines': [{'text': text, 'confidence': round(conf, 2)} for text, conf in reconstructed_lines],
            'raw_ocr_results': [{'text': result[1], 'confidence': round(result[2], 2)} for result in results]
        }), 200

    except Exception as e:
        logging.error(f"Unexpected error in /upload-receipt: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@ocr_bp.route('/debug-ocr', methods=['POST'])
def debug_ocr():
    """Debug endpoint to see raw OCR results"""
    try:
        if 'receipt' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['receipt']
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        reader = get_ocr_reader()
        if reader is None:
            return jsonify({'error': 'OCR service not available'}), 500
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        processed_path = preprocess_image(temp_path)
        results = reader.readtext(processed_path, detail=1, paragraph=False)
        
        # Clean up
        os.remove(temp_path)
        if os.path.exists(processed_path):
            os.remove(processed_path)
            
        return jsonify({
            'raw_ocr': [
                {
                    'text': result[1], 
                    'confidence': round(result[2], 2),
                    'bbox': result[0]  # Bounding box coordinates
                } for result in results
            ]
        }), 200
        
    except Exception as e:
        logging.error(f"Debug OCR failed: {str(e)}")
        return jsonify({'error': str(e)}), 500