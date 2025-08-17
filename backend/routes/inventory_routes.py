from flask import Blueprint, request, jsonify
from datetime import datetime
from bson import ObjectId
from bson.errors import InvalidId
from database import get_inventory_collection, is_db_connected
from utils import convert_item_for_json, calculate_inventory_summary, validate_price_logic
from config import Config
import logging

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route("/add-item", methods=["POST"])
def add_item():
    """Add inventory item"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        data = request.json
        print("Received inventory data:", data)
        
        # Required fields including basePrice
        required_fields = [
            "category", "itemName", "itemId", "unitSize", "stockQuantity",
            "basePrice", "sellingPrice", "mrp", "expiryDate", "gst"
        ]
        
        # Check all required fields
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] == "" or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400
        
        # Validate numeric fields
        try:
            data["stockQuantity"] = int(data["stockQuantity"])
            data["basePrice"] = float(data["basePrice"])
            data["sellingPrice"] = float(data["sellingPrice"])
            data["mrp"] = float(data["mrp"])
            data["gst"] = float(data["gst"])
        except (ValueError, TypeError) as e:
            return jsonify({"error": f"Invalid numeric value: {e}"}), 400
        
        # Validate stock quantity
        if data["stockQuantity"] < 0:
            return jsonify({"error": "Stock quantity cannot be negative"}), 400
        
        # Validate price logic
        is_valid, message = validate_price_logic(
            data["basePrice"], data["sellingPrice"], data["mrp"], data["gst"]
        )
        if not is_valid:
            return jsonify({"error": message}), 400
        
        # Connect to inventory database
        collection = get_inventory_collection()
        
        # Check if item ID already exists
        if collection.count_documents({"itemId": data["itemId"]}) > 0:
            return jsonify({"error": "Item ID already exists"}), 400
        
        # Convert expiryDate string to datetime object
        try:
            data["expiryDate"] = datetime.strptime(data["expiryDate"], "%Y-%m-%d")
        except Exception as e:
            return jsonify({"error": f"Invalid date format: {e}"}), 400
        
        # Add metadata
        data["createdAt"] = datetime.utcnow()
        data["updatedAt"] = datetime.utcnow()
        
        # Set default brand to "NA" if not provided or empty
        if not data.get("brand") or data.get("brand").strip() == "":
            data["brand"] = "NA"
        
        result = collection.insert_one(data)
        print("Inventory item added with ID:", result.inserted_id)
        
        return jsonify({
            "message": "Item added successfully",
            "id": str(result.inserted_id),
            "itemId": data["itemId"]
        }), 201
        
    except Exception as e:
        print(f"Add item error: {e}")
        logging.error(f"Add item error: {e}")
        return jsonify({"error": "Failed to add item to database"}), 500

@inventory_bp.route("/get-inventory", methods=["GET"])
def get_inventory():
    """Get all inventory items"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        collection = get_inventory_collection()
        
        # Get all items and convert for JSON
        items = []
        for item in collection.find():
            items.append(convert_item_for_json(item))
        
        return jsonify({
            "message": "Inventory retrieved successfully",
            "items": items,
            "totalItems": len(items)
        }), 200
        
    except Exception as e:
        print(f"Get inventory error: {e}")
        logging.error(f"Get inventory error: {e}")
        return jsonify({"error": "Failed to retrieve inventory"}), 500

@inventory_bp.route('/low-stock-items', methods=['GET'])
def get_low_stock_items():
    """Get items with low stock (< threshold)"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        collection = get_inventory_collection()
        
        items = []
        for item in collection.find({
            'stockQuantity': {'$lt': Config.LOW_STOCK_THRESHOLD, '$gt': 0}
        }):
            items.append(convert_item_for_json(item))
        
        return jsonify({
            'items': items,
            'count': len(items)
        }), 200
        
    except Exception as e:
        print(f"Error fetching low stock items: {e}")
        logging.error(f"Error fetching low stock items: {e}")
        return jsonify({'error': 'Failed to fetch low stock items'}), 500

@inventory_bp.route('/out-of-stock-items', methods=['GET'])
def get_out_of_stock_items():
    """Get items that are out of stock (= 0)"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        collection = get_inventory_collection()
        
        items = []
        for item in collection.find({'stockQuantity': 0}):
            items.append(convert_item_for_json(item))
        
        return jsonify({
            'items': items,
            'count': len(items)
        }), 200
        
    except Exception as e:
        print(f"Error fetching out of stock items: {e}")
        logging.error(f"Error fetching out of stock items: {e}")
        return jsonify({'error': 'Failed to fetch out of stock items'}), 500

@inventory_bp.route('/expiring-soon-items', methods=['GET'])
def get_expiring_soon_items():
    """Get items expiring within warning days"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        collection = get_inventory_collection()
        
        # Get all items to check expiry dates
        all_items = list(collection.find({}))
        expiring_items = []
        
        current_date = datetime.now()
        
        for item in all_items:
            if item.get('expiryDate'):
                try:
                    if isinstance(item['expiryDate'], str):
                        expiry_date = datetime.strptime(item['expiryDate'], '%Y-%m-%d')
                    else:
                        expiry_date = item['expiryDate']
                    days_to_expiry = (expiry_date - current_date).days
                    if 0 <= days_to_expiry <= Config.EXPIRY_WARNING_DAYS:
                        item = convert_item_for_json(item)
                        item['daysToExpiry'] = days_to_expiry
                        expiring_items.append(item)
                except:
                    pass
        
        return jsonify({
            'items': expiring_items,
            'count': len(expiring_items)
        }), 200
        
    except Exception as e:
        print(f"Error fetching expiring items: {e}")
        logging.error(f"Error fetching expiring items: {e}")
        return jsonify({'error': 'Failed to fetch expiring items'}), 500

@inventory_bp.route('/items-by-category/<category>', methods=['GET'])
def get_items_by_category(category):
    """Get all items in a specific category"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        collection = get_inventory_collection()
        
        items = []
        for item in collection.find({'category': category}):
            items.append(convert_item_for_json(item))
        
        return jsonify({
            'items': items,
            'count': len(items),
            'category': category
        }), 200
        
    except Exception as e:
        print(f"Error fetching items by category: {e}")
        logging.error(f"Error fetching items by category: {e}")
        return jsonify({'error': 'Failed to fetch items by category'}), 500

@inventory_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all unique categories in inventory"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        collection = get_inventory_collection()
        categories = collection.distinct('category')
        
        return jsonify({
            'categories': categories,
            'count': len(categories)
        }), 200
        
    except Exception as e:
        print(f"Error fetching categories: {e}")
        logging.error(f"Error fetching categories: {e}")
        return jsonify({'error': 'Failed to fetch categories'}), 500

@inventory_bp.route('/brands', methods=['GET'])
def get_brands():
    """Get all unique brands in inventory"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        collection = get_inventory_collection()
        brands = collection.distinct('brand')
        
        return jsonify({
            'brands': brands,
            'count': len(brands)
        }), 200
        
    except Exception as e:
        print(f"Error fetching brands: {e}")
        logging.error(f"Error fetching brands: {e}")
        return jsonify({'error': 'Failed to fetch brands'}), 500

@inventory_bp.route('/get-item/<item_id>', methods=['GET'])
def get_single_item(item_id):
    """Get a single item by its ID"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        try:
            object_id = ObjectId(item_id)
        except InvalidId:
            return jsonify({'error': 'Invalid item ID format'}), 400
        
        collection = get_inventory_collection()
        item = collection.find_one({'_id': object_id})
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        item = convert_item_for_json(item)
        
        return jsonify({'item': item}), 200
        
    except Exception as e:
        print(f"Error fetching single item: {e}")
        logging.error(f"Error fetching single item: {e}")
        return jsonify({'error': 'Failed to fetch item'}), 500

@inventory_bp.route("/update-item/<item_id>", methods=["PUT"])
def update_item(item_id):
    """Update an existing inventory item"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        try:
            object_id = ObjectId(item_id)
        except InvalidId:
            return jsonify({"error": "Invalid item ID format"}), 400
            
        data = request.json
        
        # Remove _id from update data if present
        data.pop("_id", None)
        
        # Add updated timestamp
        data["updatedAt"] = datetime.utcnow()
        
        # Handle date conversion if present
        if "expiryDate" in data and isinstance(data["expiryDate"], str):
            try:
                data["expiryDate"] = datetime.strptime(data["expiryDate"], "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Invalid date format"}), 400
        
        collection = get_inventory_collection()
        
        result = collection.update_one(
            {"_id": object_id},
            {"$set": data}
        )
        
        if result.matched_count == 0:
            return jsonify({"error": "Item not found"}), 404
        
        return jsonify({
            "message": "Item updated successfully",
            "modifiedCount": result.modified_count
        })
        
    except Exception as e:
        print(f"Update item error: {e}")
        logging.error(f"Update item error: {e}")
        return jsonify({"error": "Failed to update item"}), 500

@inventory_bp.route("/delete-item/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    """Delete an inventory item"""
    try:
        if not is_db_connected():
            return jsonify({"error": "Database connection not available"}), 500
            
        try:
            object_id = ObjectId(item_id)
        except InvalidId:
            return jsonify({"error": "Invalid item ID format"}), 400
        
        collection = get_inventory_collection()
        
        result = collection.delete_one({"_id": object_id})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Item not found"}), 404
        
        return jsonify({
            "message": "Item deleted successfully",
            "deletedCount": result.deleted_count
        })
        
    except Exception as e:
        print(f"Delete item error: {e}")
        logging.error(f"Delete item error: {e}")
        return jsonify({"error": "Failed to delete item"}), 500

@inventory_bp.route('/get-all-items', methods=['GET'])
def get_all_items():
    """Get all inventory items with summary"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
            
        collection = get_inventory_collection()
        
        # Fetch all items
        items = []
        for item in collection.find():
            items.append(convert_item_for_json(item))
        
        summary = calculate_inventory_summary(items)
        
        return jsonify({
            'items': items,
            'summary': summary,
            'count': len(items)
        }), 200
        
    except Exception as e:
        print(f"Error fetching items: {e}")
        logging.error(f"Error fetching items: {e}")
        return jsonify({'error': 'Failed to fetch inventory items'}), 500

@inventory_bp.route('/inventory-stats', methods=['GET'])
def inventory_stats():
    """Get inventory statistics"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
            
        collection = get_inventory_collection()
        
        # Get all items for calculation
        items = []
        for item in collection.find():
            items.append(convert_item_for_json(item))
            
        summary = calculate_inventory_summary(items)
        return jsonify(summary), 200
        
    except Exception as e:
        print(f"Error fetching stats: {e}")
        logging.error(f"Error fetching stats: {e}")
        return jsonify({'error': 'Failed to fetch inventory statistics'}), 500

@inventory_bp.route('/search-items', methods=['GET'])
def search_items():
    """Search items by name, brand, or category"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        query = request.args.get('q', '').strip()
        category = request.args.get('category', '').strip()
        brand = request.args.get('brand', '').strip()
        
        if not query and not category and not brand:
            return jsonify({'items': [], 'count': 0}), 200
        
        collection = get_inventory_collection()
        
        # Build search filter
        search_filter = {}
        
        if query:
            search_filter['$or'] = [
                {'itemName': {'$regex': query, '$options': 'i'}},
                {'brand': {'$regex': query, '$options': 'i'}},
                {'itemId': {'$regex': query, '$options': 'i'}}
            ]
        
        if category:
            search_filter['category'] = category
        
        if brand:
            search_filter['brand'] = brand
        
        items = []
        for item in collection.find(search_filter):
            items.append(convert_item_for_json(item))
        
        return jsonify({
            'items': items,
            'count': len(items)
        }), 200
        
    except Exception as e:
        print(f"Error searching items: {e}")
        logging.error(f"Error searching items: {e}")
        return jsonify({'error': 'Failed to search items'}), 500

@inventory_bp.route('/update-stock/<item_id>', methods=['PATCH'])
def update_stock(item_id):
    """Update stock quantity for a specific item"""
    try:
        if not is_db_connected():
            return jsonify({'error': 'Database connection not available'}), 500
        
        try:
            object_id = ObjectId(item_id)
        except InvalidId:
            return jsonify({'error': 'Invalid item ID format'}), 400
        
        data = request.json
        
        if 'stockQuantity' not in data:
            return jsonify({'error': 'stockQuantity is required'}), 400
        
        try:
            new_stock = int(data['stockQuantity'])
            if new_stock < 0:
                return jsonify({'error': 'Stock quantity cannot be negative'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid stock quantity value'}), 400
        
        collection = get_inventory_collection()
        
        result = collection.update_one(
            {'_id': object_id},
            {'$set': {
                'stockQuantity': new_stock,
                'updatedAt': datetime.utcnow()
            }}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Item not found'}), 404
        
        return jsonify({
            'message': 'Stock updated successfully',
            'newStock': new_stock
        }), 200
        
    except Exception as e:
        print(f"Error updating stock: {e}")
        logging.error(f"Error updating stock: {e}")
        return jsonify({'error': 'Failed to update stock'}), 500