from flask import Blueprint, request, jsonify
from database import get_user_collection, get_inventory_collection
import re
import logging
from bson import ObjectId

search_bp = Blueprint('search', __name__, url_prefix='/api')

@search_bp.route('/search-customers', methods=['GET'])
def search_customers():
    """
    Search customers by fullName, kiranaId, or mobile
    """
    try:
        query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify([]), 200
        
        if len(query) > 100:  # Basic input validation
            return jsonify({'error': 'Query too long'}), 400
        
        # Get database collection
        signups_collection = get_user_collection()
        
        # Create case-insensitive regex pattern for partial matching
        regex_pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        # Search across multiple fields
        search_criteria = {
            '$or': [
                {'fullName': {'$regex': regex_pattern}},
                {'kiranaId': {'$regex': regex_pattern}},
                {'mobile': {'$regex': regex_pattern}}
            ]
        }
        
        # Find matching customers, limit to 10 results
        customers = list(signups_collection.find(
                        search_criteria,
                        {
                            '_id': 1,
                            'fullName': 1,
                            'mobile': 1,
                            'role': 1,
                            'kiranaId': 1,
                            'isVerified': 1,
                            'dateOfBirth': 1,
                            'loyalty_points': 1
                        }
                    ).limit(10))
        
        # Convert ObjectId to string and format response
        formatted_customers = []
        for customer in customers:
            formatted_customer = {
                'id': str(customer['_id']),
                'name': customer.get('fullName', 'Unknown'),
                'kirana_id': str(customer.get('kiranaId', '')),  # Convert to string
                'phone': str(customer.get('mobile', '')),  # Convert to string
                'role': customer.get('role', ''),
                'is_verified': customer.get('isVerified', False),
                'date_of_birth': customer.get('dateOfBirth', ''),
                'loyalty_points': int(customer.get('loyalty_points', 0))
            }
            formatted_customers.append(formatted_customer)
        
        # Sort by relevance (exact matches first, then partial matches)
        def sort_key(item):
            # Safely convert all fields to strings before calling lower()
            name = str(item['name']).lower()
            kirana_id = str(item.get('kirana_id', '')).lower()
            phone = str(item.get('phone', '')).lower()
            query_lower = query.lower()
            
            # Exact match gets highest priority
            if query_lower == name or query_lower == kirana_id or query_lower == phone:
                return 0
            # Starts with gets second priority
            elif name.startswith(query_lower) or kirana_id.startswith(query_lower) or phone.startswith(query_lower):
                return 1
            # Contains gets third priority
            else:
                return 2
        
        formatted_customers.sort(key=sort_key)
        
        return jsonify(formatted_customers), 200
        
    except Exception as e:
        logging.error(f"Error searching customers: {str(e)}")
        return jsonify({'error': 'Failed to search customers'}), 500

@search_bp.route('/search-products', methods=['GET'])
def search_products():
    """
    Search products by itemName, brand, category, or unitSize
    """
    try:
        query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify([]), 200
        
        if len(query) > 100:  # Basic input validation
            return jsonify({'error': 'Query too long'}), 400
        
        # Get database collection
        items_collection = get_inventory_collection()
        
        # Create case-insensitive regex pattern for partial matching
        regex_pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        # Search across multiple fields
        search_criteria = {
            '$or': [
                {'itemName': {'$regex': regex_pattern}},
                {'brand': {'$regex': regex_pattern}},
                {'category': {'$regex': regex_pattern}},
                {'unitSize': {'$regex': regex_pattern}},
                {'itemId': {'$regex': regex_pattern}}
            ],
            # Only show items that are in stock
            'stockQuantity': {'$gt': 0}
        }
        
        # Find matching products, limit to 15 results
        products = list(items_collection.find(
            search_criteria,
            {
                '_id': 1,
                'itemId': 1,
                'itemName': 1,
                'brand': 1,
                'category': 1,
                'unitSize': 1,
                'mrp': 1,
                'stockQuantity': 1,
                'basePrice': 1,
                'sellingPrice': 1
            }
        ).limit(15))
        
        # Convert ObjectId to string and format response
        formatted_products = []
        for product in products:
            formatted_product = {
                'id': str(product['_id']),
                'item_id': product.get('itemId', ''),
                'item_name': product.get('itemName', 'Unknown Item'),
                'brand': product.get('brand', ''),
                'category': product.get('category', ''),
                'unit_size': product.get('unitSize', ''),
                'mrp': float(product.get('mrp', 0)),
                'base_price': float(product.get('basePrice', 0)),
                'selling_price': float(product.get('sellingPrice', 0)),
                'stock_quantity': int(product.get('stockQuantity', 0))
            }
            formatted_products.append(formatted_product)
        
        # Sort by relevance (exact matches first, then partial matches)
        def sort_key(item):
            name = item['item_name'].lower()
            brand = item.get('brand', '').lower()
            query_lower = query.lower()
            
            # Exact match gets highest priority
            if query_lower == name or query_lower == brand:
                return 0
            # Starts with gets second priority
            elif name.startswith(query_lower) or brand.startswith(query_lower):
                return 1
            # Contains gets third priority
            else:
                return 2
        
        formatted_products.sort(key=sort_key)
        
        return jsonify(formatted_products), 200
        
    except Exception as e:
        logging.error(f"Error searching products: {str(e)}")
        return jsonify({'error': 'Failed to search products'}), 500

@search_bp.route('/customer/<customer_id>', methods=['GET'])
def get_customer_details(customer_id):
    """
    Get detailed customer information by ID
    """
    try:
        if not ObjectId.is_valid(customer_id):
            return jsonify({'error': 'Invalid customer ID'}), 400
        
        # Get database collection
        signups_collection = get_user_collection()
        
        # Find customer by ID
        customer = signups_collection.find_one(
                    {'_id': ObjectId(customer_id)},
                    {
                        '_id': 1,
                        'fullName': 1,
                        'kiranaId': 1,
                        'mobile': 1,
                        'role': 1,
                        'isVerified': 1,
                        'dateOfBirth': 1,
                        'createdAt': 1,
                        'lastLoginAt': 1,
                        'loyalty_points': 1
                    }
                )
        
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        # Format response
        formatted_customer = {
            'id': str(customer['_id']),
            'name': customer.get('fullName', 'Unknown'),
            'kirana_id': customer.get('kiranaId', ''),
            'phone': customer.get('mobile', ''),
            'role': customer.get('role', ''),
            'is_verified': customer.get('isVerified', False),
            'date_of_birth': customer.get('dateOfBirth', ''),
            'created_at': customer.get('createdAt', ''),
            'last_login_at': customer.get('lastLoginAt', ''),
            'loyalty_points': int(customer.get('loyalty_points', 0))
        }
        
        return jsonify(formatted_customer), 200
        
    except Exception as e:
        logging.error(f"Error getting customer details: {str(e)}")
        return jsonify({'error': 'Failed to get customer details'}), 500

@search_bp.route('/product/<product_id>', methods=['GET'])
def get_product_details(product_id):
    """
    Get detailed product information by ID
    """
    try:
        if not ObjectId.is_valid(product_id):
            return jsonify({'error': 'Invalid product ID'}), 400
        
        # Get database collection
        items_collection = get_inventory_collection()
        
        # Find product by ID
        product = items_collection.find_one(
            {'_id': ObjectId(product_id)},
            {
                '_id': 1,
                'itemId': 1,
                'itemName': 1,
                'brand': 1,
                'category': 1,
                'unitSize': 1,
                'mrp': 1,
                'basePrice': 1,
                'sellingPrice': 1,
                'stockQuantity': 1,
                'gst': 1,
                'expiryDate': 1,
                'createdAt': 1,
                'updatedAt': 1
            }
        )
        
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Format response
        formatted_product = {
            'id': str(product['_id']),
            'item_id': product.get('itemId', ''),
            'item_name': product.get('itemName', 'Unknown Item'),
            'brand': product.get('brand', ''),
            'category': product.get('category', ''),
            'unit_size': product.get('unitSize', ''),
            'mrp': float(product.get('mrp', 0)),
            'base_price': float(product.get('basePrice', 0)),
            'selling_price': float(product.get('sellingPrice', 0)),
            'stock_quantity': int(product.get('stockQuantity', 0)),
            'gst': float(product.get('gst', 0)),
            'expiry_date': product.get('expiryDate', ''),
            'created_at': product.get('createdAt', ''),
            'updated_at': product.get('updatedAt', '')
        }
        
        return jsonify(formatted_product), 200
        
    except Exception as e:
        logging.error(f"Error getting product details: {str(e)}")
        return jsonify({'error': 'Failed to get product details'}), 500