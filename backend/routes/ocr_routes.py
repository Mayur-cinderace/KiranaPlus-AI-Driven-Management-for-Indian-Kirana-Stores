from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import os
import logging
from datetime import datetime
from ocr_service import get_ocr_reader, allowed_file, preprocess_image, reconstruct_receipt_lines, fuzzy_match_inventory_item, parse_ocr_results
from config import Config
from database import get_inventory_collection, get_receipts_collection
from bson import ObjectId
import re
from utils import get_inventory_items_from_db

ocr_bp = Blueprint('ocr', __name__)

def extract_items_from_text(texts_with_confidence):
    """Extract item names from OCR text lines, matching to inventory items"""
    items = []
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
            line = re.sub(r'[*/×\-–]', ' ', line)
            line = re.sub(r'[^a-z0-9\s]', '', line)
            line = re.sub(r'\s+', ' ', line).strip()
            
            print(f"Processing line: '{original_line}' -> '{line}' (confidence: {confidence:.2f})")
            
            name_part = line.strip()
            if not re.search(r'[a-z]', name_part) or len(name_part) < 2:
                continue
                
            # Fuzzy match to inventory
            match = fuzzy_match_inventory_item(name_part, inventory_items)
            
            if match:
                final_name = match['inventory_item']['itemName']
                item = {
                    "item": final_name,
                    "quantity": None,  # Quantity entered manually in frontend
                    "confidence": round(confidence, 2),
                    "fuzzy_match": {
                        "similarity_score": round(match['similarity_score'], 3),
                        "original_extracted": name_part,
                        "matched_field": match['matched_field'],
                        "inventory_id": str(match['inventory_item'].get('_id', '')),
                        "item_id": match['inventory_item'].get('itemId', ''),
                        "selling_price": match['inventory_item'].get('sellingPrice'),
                        "mrp": match['inventory_item'].get('mrp')
                    }
                }
                print(f"✓ Added matched item: {final_name} (similarity: {match['similarity_score']:.3f})")
            else:
                item = {
                    "item": name_part.title(),
                    "quantity": None,
                    "confidence": round(confidence, 2),
                    "fuzzy_match": None
                }
                print(f"✓ Added non-matched item: {name_part.title()}")
            
            items.append(item)
            
        except Exception as e:
            logging.warning(f"Error processing line '{text}': {str(e)}")
            continue
    
    return items

@ocr_bp.route('/upload-receipt', methods=['POST'])
def upload_receipt():
    """Upload and process receipt image using OCR to extract item names"""
    try:
        reader = get_ocr_reader()
        if reader is None:
            logging.error("PaddleOCR not initialized")
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
            print("Extracting text with PaddleOCR...")
            results = reader.ocr(processed_path)
            print(f"Raw OCR results type: {type(results)}")
            
            # Use the new parsing function
            ocr_results = parse_ocr_results(results)
            print(f"OCR completed. Found {len(ocr_results)} text elements.")
            
            reconstructed_lines = reconstruct_receipt_lines(ocr_results)
            print(f"Reconstructed into {len(reconstructed_lines)} lines:")
            for line, conf in reconstructed_lines:
                print(f"  Line: '{line}' (confidence: {conf:.2f})")
            
        except Exception as e:
            logging.error(f"PaddleOCR failed for {processed_path}: {str(e)}")
            return jsonify({'error': 'Text extraction failed'}), 500

        print("\n=== Processing reconstructed lines ===")
        items = extract_items_from_text(reconstructed_lines)
        
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
            'raw_ocr_results': [{'text': result[1], 'confidence': round(result[2], 2)} for result in ocr_results]
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
        results = reader.ocr(processed_path)
        
        # Use the new parsing function
        ocr_results = parse_ocr_results(results)
        
        os.remove(temp_path)
        if os.path.exists(processed_path):
            os.remove(processed_path)
            
        return jsonify({
            'raw_ocr': [
                {
                    'text': result[1], 
                    'confidence': round(result[2], 2),
                    'bbox': result[0]
                } for result in ocr_results
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
                        {'sellingPrice': 1}
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
                    <td>₹{:.2f}</td>
                    <td>₹{:.2f}</td>
                </tr>
            """.format(index, item['itemName'], item['quantity'], item['sellingPrice'], item_total)

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
        """.format(total_amount)

        return jsonify({'html': html}), 200

    except Exception as e:
        logging.error(f"Error generating bill: {str(e)}")
        return jsonify({'error': 'Failed to generate bill'}), 500