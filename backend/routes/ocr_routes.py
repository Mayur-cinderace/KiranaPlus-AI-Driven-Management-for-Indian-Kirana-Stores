from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import logging
import re
from datetime import datetime
from ocr_service import get_ocr_reader, allowed_file, preprocess_image, reconstruct_receipt_lines, get_intelligent_unit_fallback
from config import Config
from database import get_inventory_collection, get_receipts_collection
from bson import ObjectId
from utils import get_inventory_items_from_db

ocr_bp = Blueprint('ocr', __name__)

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

def extract_items_from_text(texts_with_confidence):
    """Enhanced version with closest Levenshtein distance matching to inventory items.
    Quantities are set to None for manual entry in frontend."""
    items = []
    valid_units = ['kg', 'g', 'pc', 'pcs', 'gram', 'grams', 'piece', 'pieces', 
                   'ltr', 'litre', 'liter', 'ml', 'c', 'cup', 'cups', 'bottle', 'bottles',
                   'k6', 'k0', 'gu']
    
    unit_mapping = {
        'gm': 'g', 'gms': 'g', 'kgs': 'kg', 'k6': 'kg', 'k0': 'kg', 'gu': 'g',
        'l': 'ltr', 'liters': 'ltr', 'litres': 'ltr', 'pcs': 'pc', 'pieces': 'pc'
    }
    
    inventory_items = get_inventory_items_from_db()
    
    for text, confidence in texts_with_confidence:
        if confidence < 0.25:
            continue
            
        try:
            original_line = text
            line = text.lower().strip()
            
            if len(line) < 2:
                continue
            
            line = re.sub(r'[<>]', '', line)
            line = re.sub(r':', '', line)
            line = re.sub(r'[*/×\-–]', ' x ', line)
            line = re.sub(r'[^a-z0-9\s.x]', '', line)
            line = re.sub(r'\b(\d+)k\b(?![0-9])', lambda m: str(int(m.group(1)) * 1000), line)
            line = re.sub(r'\s+', ' ', line).strip()
            
            print(f"Processing line: '{original_line}' -> '{line}' (confidence: {confidence:.2f})")
            
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
                    unit_part = match.group(3).strip() if len(match.groups()) > 2 and match.group(3) else ''
                    
                    if not re.search(r'[a-z]', name_part) or len(name_part) < 2:
                        continue
                    
                    if inventory_items:
                        distances = [(item, levenshtein_distance(name_part.lower(), item['itemName'].lower())) for item in inventory_items]
                        closest_item, min_dist = min(distances, key=lambda x: x[1])
                        max_len = max(len(name_part), len(closest_item['itemName']))
                        similarity_score = 1 - (min_dist / max_len) if max_len > 0 else 0
                        
                        final_name = closest_item['itemName']
                        inventory_unit = closest_item.get('unitSize', '').lower()
                        if inventory_unit and inventory_unit in valid_units:
                            final_unit = inventory_unit
                        elif unit_part:
                            final_unit = unit_mapping.get(unit_part, unit_part)
                        else:
                            final_unit = get_intelligent_unit_fallback(final_name)
                        
                        item = {
                            "item": final_name,
                            "quantity": None,  # Set to None for manual entry
                            "unit": final_unit,
                            "confidence": round(confidence, 2),
                            "fuzzy_match": {
                                "similarity_score": round(similarity_score, 3),
                                "original_extracted": name_part,
                                "matched_field": "itemName",
                                "inventory_id": str(closest_item.get('_id', '')),
                                "item_id": closest_item.get('itemId', ''),
                                "selling_price": closest_item.get('sellingPrice'),
                                "mrp": closest_item.get('mrp')
                            }
                        }
                        
                        print(f"✓ Added closest matched item: {final_name} (distance: {min_dist}, similarity: {similarity_score:.3f})")
                        
                    else:
                        if unit_part in unit_mapping:
                            unit_part = unit_mapping[unit_part]
                        elif not unit_part or unit_part not in valid_units:
                            intelligent_unit = get_intelligent_unit_fallback(name_part)
                            unit_part = intelligent_unit
                            print(f"Applied intelligent unit fallback: '{name_part}' -> '{intelligent_unit}'")
                        
                        item = {
                            "item": name_part.title(),
                            "quantity": None,
                            "unit": unit_part if unit_part else None,
                            "confidence": round(confidence, 2),
                            "fuzzy_match": None
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

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        if file_size > Config.MAX_FILE_SIZE:
            logging.error(f"File too large: {file_size} bytes")
            return jsonify({'error': 'File too large. Maximum size is 5MB'}), 400
        file.seek(0)

        filename = secure_filename(file.filename)
        temp_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        
        try:
            file.save(temp_path)
            print(f"File saved to: {temp_path}")
        except Exception as e:
            logging.error(f"Failed to save file {filename}: {str(e)}")
            return jsonify({'error': 'Failed to save uploaded file'}), 500

        try:
            processed_path = preprocess_image(temp_path)
        except Exception as e:
            logging.error(f"Image processing failed for {filename}: {str(e)}")
            return jsonify({'error': 'Failed to process image'}), 500

        try:
            print("Extracting text with EasyOCR...")
            results = reader.readtext(processed_path, detail=1, paragraph=False)
            print(f"OCR completed. Found {len(results)} text elements.")
            
            reconstructed_lines = reconstruct_receipt_lines(results)
            print(f"Reconstructed into {len(reconstructed_lines)} lines:")
            for line, conf in reconstructed_lines:
                print(f"  Line: '{line}' (confidence: {conf:.2f})")
            
            individual_fragments = [(result[1], result[2]) for result in results]
            print("Individual fragments:", [(text, f"{conf:.2f}") for text, conf in individual_fragments])
            
        except Exception as e:
            logging.error(f"EasyOCR failed for {processed_path}: {str(e)}")
            return jsonify({'error': 'Text extraction failed'}), 500

        print("\n=== Processing reconstructed lines ===")
        items_from_lines = extract_items_from_text(reconstructed_lines)
        
        print("\n=== Processing individual fragments ===")
        items_from_fragments = extract_items_from_text(individual_fragments)
        
        all_items = items_from_lines + items_from_fragments
        
        seen_items = set()
        unique_items = []
        for item in all_items:
            item_key = item['item'].lower()
            if item_key not in seen_items:
                seen_items.add(item_key)
                unique_items.append(item)
        
        items = unique_items

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
        
        os.remove(temp_path)
        if os.path.exists(processed_path):
            os.remove(processed_path)
            
        return jsonify({
            'raw_ocr': [
                {
                    'text': result[1], 
                    'confidence': round(result[2], 2),
                    'bbox': result[0]
                } for result in results
            ]
        }), 200
        
    except Exception as e:
        logging.error(f"Debug OCR failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@ocr_bp.route('/save-receipt-items', methods=['POST'])
def save_receipt_items():
    """Save receipt items with manually entered quantities and update inventory"""
    try:
        data = request.get_json()
        items = data.get('items', [])
        if not items:
            logging.error("No items provided in save-receipt-items request")
            return jsonify({'error': 'No items provided'}), 400

        receipts_collection = get_receipts_collection()
        inventory_collection = get_inventory_collection()

        enriched_items = []
        for item in items:
            if not item.get('item') or item.get('quantity') is None or item['quantity'] <= 0:
                logging.warning(f"Invalid item or quantity: {item.get('item', 'unknown')}")
                return jsonify({'error': f'Invalid item or quantity for {item.get("item", "unknown")}'}), 400

            inventory_id = item.get('fuzzy_match', {}).get('inventory_id')
            selling_price = None
            if inventory_id:
                try:
                    inventory_item = inventory_collection.find_one(
                        {'_id': ObjectId(inventory_id)},
                        {'sellingPrice': 1, 'unitSize': 1}
                    )
                    if inventory_item:
                        selling_price = inventory_item.get('sellingPrice', 0)
                        result = inventory_collection.update_one(
                            {'_id': ObjectId(inventory_id)},
                            {
                                '$inc': {'stockQuantity': item['quantity']},
                                '$set': {'updatedAt': datetime.utcnow().isoformat()}
                            }
                        )
                        if result.matched_count == 0:
                            logging.warning(f"No inventory item found for ID: {inventory_id}")
                    else:
                        logging.warning(f"No inventory item found for ID: {inventory_id}")
                except Exception as e:
                    logging.warning(f"Failed to update inventory for {item['item']}: {str(e)}")

            enriched_item = {
                'itemName': item['item'],
                'quantity': item['quantity'],
                'unit': item['unit'],
                'inventory_id': inventory_id,
                'sellingPrice': selling_price if selling_price is not None else item.get('fuzzy_match', {}).get('selling_price', 0),
                'mrp': item.get('fuzzy_match', {}).get('mrp'),
                'timestamp': datetime.utcnow().isoformat()
            }
            enriched_items.append(enriched_item)

        receipt_id = receipts_collection.insert_one({
            'items': enriched_items,
            'createdAt': datetime.utcnow().isoformat(),
            'updatedAt': datetime.utcnow().isoformat()
        }).inserted_id

        logging.info(f"Saved receipt with ID: {receipt_id}")
        return jsonify({
            'message': 'Items saved successfully',
            'receipt_id': str(receipt_id),
            'items': enriched_items
        }), 200

    except Exception as e:
        logging.error(f"Error saving receipt items: {str(e)}")
        return jsonify({'error': 'Failed to save items'}), 500

@ocr_bp.route('/generate-bill', methods=['POST'])
def generate_bill():
    """Generate an HTML bill preview"""
    try:
        data = request.get_json()
        items = data.get('items', [])
        if not items:
            logging.error("No items provided in generate-bill request")
            return jsonify({'error': 'No items provided'}), 400

        total_amount = 0
        html = """
        <div class="p-6 font-mono text-sm leading-6 bg-white dark:bg-slate-900 border border-gray-200 dark:border-gray-700 rounded-xl">
            <div class="text-center mb-4">
                <h2 class="text-2xl font-bold">Kirana Store</h2>
                <p class="text-sm">123 Market Street, City, State, ZIP</p>
                <p class="text-sm">Phone: (123) 456-7890</p>
                <p class="text-sm">Date: {} </p>
            </div>
            <hr class="border-t border-gray-300 dark:border-gray-600 my-4">
            <table class="w-full mb-4">
                <thead>
                    <tr class="text-left">
                        <th class="w-10">Sl.</th>
                        <th>Item</th>
                        <th class="w-20">Qty</th>
                        <th class="w-20">Unit</th>
                        <th class="w-20">Price</th>
                        <th class="w-20">Total</th>
                    </tr>
                </thead>
                <tbody>
        """.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        for index, item in enumerate(items, 1):
            if item['quantity'] <= 0 or not item.get('sellingPrice'):
                continue
            item_total = item['quantity'] * item['sellingPrice']
            total_amount += item_total
            html += """
                <tr>
                    <td>{}</td>
                    <td>{}</td>
                    <td>{:.2f}</td>
                    <td>{}</td>
                    <td>₹{:.2f}</td>
                    <td>₹{:.2f}</td>
                </tr>
            """.format(index, item['itemName'], item['quantity'], item['unit'], item['sellingPrice'], item_total)

        html += """
                </tbody>
            </table>
            <hr class="border-t border-gray-300 dark:border-gray-600 my-4">
            <div class="text-right">
                <p class="font-bold">Grand Total: ₹{:.2f}</p>
            </div>
            <div class="text-center mt-4">
                <p class="text-sm">Thank you for shopping with us!</p>
            </div>
        </div>
        """

        return jsonify({'html': html}), 200

    except Exception as e:
        logging.error(f"Error generating bill: {str(e)}")
        return jsonify({'error': 'Failed to generate bill'}), 500