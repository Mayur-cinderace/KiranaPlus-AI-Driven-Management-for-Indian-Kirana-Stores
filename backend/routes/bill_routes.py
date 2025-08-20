from flask import Blueprint, request, jsonify
from database import get_inventory_collection, get_user_collection, get_bills_collection
from datetime import datetime
import logging
from bson import ObjectId
import pymongo

bill_bp = Blueprint('bill', __name__, url_prefix='/api')

@bill_bp.route('/create-bill', methods=['POST'])
def create_bill():
    """
    Create a new bill, update stock quantities, and generate receipt
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        customer_id = data.get('customer_id')
        items = data.get('items', [])
        payment_method = data.get('payment_method', 'cash')
        discount = float(data.get('discount', 0))
        
        if not items:
            return jsonify({'error': 'No items in bill'}), 400
        
        # Get database collections - FIXED: Check for None instead of truthiness
        items_collection = get_inventory_collection()
        users_collection = get_user_collection()
        bills_collection = get_bills_collection()
        
        if items_collection is None or bills_collection is None:
            return jsonify({'error': 'Database connection failed'}), 500
        
        # Validate customer if provided
        customer_info = None
        if customer_id and ObjectId.is_valid(customer_id):
            if users_collection is not None:
                customer_info = users_collection.find_one({'_id': ObjectId(customer_id)})
        
        # Validate items and check stock availability
        validated_items = []
        total_amount = 0
        
        for item in items:
            item_id = item.get('item_id')
            quantity = int(item.get('quantity', 0))
            
            if not item_id or quantity <= 0:
                return jsonify({'error': f'Invalid item data: {item}'}), 400
            
            # Find product in database
            if ObjectId.is_valid(item_id):
                product = items_collection.find_one({'_id': ObjectId(item_id)})
            else:
                product = items_collection.find_one({'itemId': item_id})
            
            if not product:
                return jsonify({'error': f'Product not found: {item_id}'}), 404
            
            # Check stock availability
            current_stock = int(product.get('stockQuantity', 0))
            if current_stock < quantity:
                return jsonify({
                    'error': f'Insufficient stock for {product.get("itemName", "Unknown")}. Available: {current_stock}, Requested: {quantity}'
                }), 400
            
            # Calculate item total
            selling_price = float(product.get('sellingPrice', 0))
            item_total = selling_price * quantity
            total_amount += item_total
            
            validated_items.append({
                'product_id': str(product['_id']),
                'item_id': product.get('itemId', ''),
                'item_name': product.get('itemName', ''),
                'brand': product.get('brand', ''),
                'unit_size': product.get('unitSize', ''),
                'selling_price': selling_price,
                'mrp': float(product.get('mrp', 0)),
                'quantity': quantity,
                'item_total': item_total,
                'gst': float(product.get('gst', 0))
            })
        
        # Apply discount
        discount_amount = (total_amount * discount) / 100 if discount > 0 else 0
        loyalty_points_used = int(data.get('loyalty_points_used', 0))
        loyalty_discount_amount = loyalty_points_used * 2  # 1 point = ₹2
        final_amount = total_amount - discount_amount - loyalty_discount_amount

        # Calculate points earned
        points_earned = int(total_amount / 20)
        
        # Calculate total GST
        total_gst = sum((item['item_total'] * item['gst']) / 100 for item in validated_items)
        
        # Generate bill number
        bill_number = f"BILL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create bill document
        bill_data = {
            'bill_number': bill_number,
            'customer_id': customer_id if customer_info else None,
            'customer_name': customer_info.get('fullName', 'Walk-in Customer') if customer_info else 'Walk-in Customer',
            'customer_phone': customer_info.get('mobile', '') if customer_info else '',
            'customer_kirana_id': customer_info.get('kiranaId', '') if customer_info else '',
            'items': validated_items,
            'subtotal': total_amount,
            'discount_percentage': discount,
            'discount_amount': discount_amount,
            'loyalty_points_used': loyalty_points_used,
            'loyalty_discount_amount': loyalty_discount_amount,
            'points_earned': points_earned,
            'total_gst': total_gst,
            'final_amount': final_amount,
            'payment_method': payment_method,
            'created_at': datetime.now(),
            'created_by': 'system',  # You can update this with actual user info
            'status': 'completed'
        }
        
        # Start a transaction to ensure data consistency
# Start a transaction to ensure data consistency
        with items_collection.database.client.start_session() as session:
            with session.start_transaction():
                # Update stock quantities
                for item in validated_items:
                    result = items_collection.update_one(
                        {'_id': ObjectId(item['product_id'])},
                        {
                            '$inc': {'stockQuantity': -item['quantity']},
                            '$set': {'updatedAt': datetime.now()}
                        },
                        session=session
                    )
                    
                    if result.modified_count == 0:
                        raise Exception(f"Failed to update stock for item: {item['item_name']}")
                
                # Update customer loyalty points if applicable
                if customer_info and customer_id and ObjectId.is_valid(customer_id):
                    current_points = int(customer_info.get('loyalty_points', 0))
                    new_points = current_points - loyalty_points_used + points_earned
                    points_update_result = users_collection.update_one(
                        {'_id': ObjectId(customer_id)},
                        {
                            '$set': {
                                'loyalty_points': new_points,
                                'updated_at': datetime.now()
                            }
                        },
                        session=session
                    )
                    if points_update_result.modified_count == 0:
                        raise Exception(f"Failed to update loyalty points for customer: {customer_id}")
                
                # Save bill to database
                bill_result = bills_collection.insert_one(bill_data, session=session)
                if not bill_result.inserted_id:
                    raise Exception("Failed to save bill to database")
                
        # Generate receipt data
        receipt_data = {
            'bill_number': bill_number,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'customer': {
                'name': bill_data['customer_name'],
                'phone': bill_data['customer_phone']
            },
            'items': validated_items,
            'summary': {
                'subtotal': total_amount,
                'discount_percentage': discount,
                'discount_amount': discount_amount,
                'total_gst': total_gst,
                'final_amount': final_amount,
                'payment_method': payment_method
            }
        }
        
        logging.info(f"Bill created successfully: {bill_number}")
        
        return jsonify({
            'success': True,
            'message': 'Bill created successfully',
            'bill_number': bill_number,
            'bill_id': str(bill_result.inserted_id),
            'receipt': receipt_data
        }), 201
        
    except Exception as e:
        logging.error(f"Error creating bill: {str(e)}")
        return jsonify({'error': f'Failed to create bill: {str(e)}'}), 500

@bill_bp.route('/get-bill/<bill_number>', methods=['GET'])
def get_bill(bill_number):
    """
    Get bill details by bill number
    """
    try:
        bills_collection = get_bills_collection()
        if bills_collection is None:  # FIXED: Check for None instead of truthiness
            return jsonify({'error': 'Database connection failed'}), 500
        
        bill = bills_collection.find_one({'bill_number': bill_number})
        
        if not bill:
            return jsonify({'error': 'Bill not found'}), 404
        
        # Convert ObjectId to string for JSON serialization
        bill['_id'] = str(bill['_id'])
        bill['loyalty_points_used'] = bill.get('loyalty_points_used', 0)
        bill['loyalty_discount_amount'] = bill.get('loyalty_discount_amount', 0)
        bill['points_earned'] = bill.get('points_earned', 0)
        
        return jsonify(bill), 200
        
    except Exception as e:
        logging.error(f"Error getting bill: {str(e)}")
        return jsonify({'error': 'Failed to get bill'}), 500

@bill_bp.route('/print-receipt/<bill_number>', methods=['GET'])
def get_receipt(bill_number):
    """
    Get receipt data for printing
    """
    try:
        bills_collection = get_bills_collection()
        if bills_collection is None:  # FIXED: Check for None instead of truthiness
            return jsonify({'error': 'Database connection failed'}), 500
        
        bill = bills_collection.find_one({'bill_number': bill_number})
        
        if not bill:
            return jsonify({'error': 'Receipt not found'}), 404
        
        # Generate receipt data
        receipt_data = {
            'bill_number': bill['bill_number'],
            'date': bill['created_at'].strftime('%Y-%m-%d %H:%M:%S'),
            'customer': {
                'name': bill['customer_name'],
                'phone': bill['customer_phone']
            },
            'items': bill['items'],
            'summary': {
                'subtotal': bill['subtotal'],
                'discount_percentage': bill['discount_percentage'],
                'discount_amount': bill['discount_amount'],
                'loyalty_points_used': bill.get('loyalty_points_used', 0),
                'loyalty_discount_amount': bill.get('loyalty_discount_amount', 0),
                'points_earned': bill.get('points_earned', 0),
                'total_gst': bill['total_gst'],
                'final_amount': bill['final_amount'],
                'payment_method': bill['payment_method']
            }
        }
        
        return jsonify(receipt_data), 200
        
    except Exception as e:
        logging.error(f"Error getting receipt: {str(e)}")
        return jsonify({'error': 'Failed to get receipt'}), 500

@bill_bp.route('/validate-stock', methods=['POST'])
def validate_stock():
    """
    Validate stock availability before creating bill
    """
    try:
        data = request.get_json()
        items = data.get('items', [])
        
        if not items:
            return jsonify({'error': 'No items provided'}), 400
        
        items_collection = get_inventory_collection()
        if items_collection is None:  # FIXED: Check for None instead of truthiness
            return jsonify({'error': 'Database connection failed'}), 500
        
        validation_results = []
        
        for item in items:
            item_id = item.get('item_id')
            quantity = int(item.get('quantity', 0))
            
            if ObjectId.is_valid(item_id):
                product = items_collection.find_one({'_id': ObjectId(item_id)})
            else:
                product = items_collection.find_one({'itemId': item_id})
            
            if not product:
                validation_results.append({
                    'item_id': item_id,
                    'valid': False,
                    'message': 'Product not found'
                })
                continue
            
            current_stock = int(product.get('stockQuantity', 0))
            is_valid = current_stock >= quantity
            
            validation_results.append({
                'item_id': item_id,
                'item_name': product.get('itemName', ''),
                'requested_quantity': quantity,
                'available_stock': current_stock,
                'valid': is_valid,
                'message': 'OK' if is_valid else f'Insufficient stock. Available: {current_stock}'
            })
        
        all_valid = all(result['valid'] for result in validation_results)
        
        return jsonify({
            'valid': all_valid,
            'items': validation_results
        }), 200
        
    except Exception as e:
        logging.error(f"Error validating stock: {str(e)}")
        return jsonify({'error': 'Failed to validate stock'}), 500

@bill_bp.route('/bills', methods=['GET'])
def get_all_bills():
    """
    Get all bills with pagination
    """
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        bills_collection = get_bills_collection()
        if bills_collection is None:  # FIXED: Check for None instead of truthiness
            return jsonify({'error': 'Database connection failed'}), 500
        
        # Calculate skip value for pagination
        skip = (page - 1) * per_page
        
        # Get bills with pagination, sorted by creation date (newest first)
        bills_cursor = bills_collection.find({}).sort('created_at', -1).skip(skip).limit(per_page)
        bills = list(bills_cursor)
        
        # Convert ObjectIds to strings
        for bill in bills:
            bill['_id'] = str(bill['_id'])
        
        # Get total count for pagination info
        total_bills = bills_collection.count_documents({})
        total_pages = (total_bills + per_page - 1) // per_page
        
        return jsonify({
            'bills': bills,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_bills': total_bills,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        }), 200
        
    except Exception as e:
        logging.error(f"Error getting bills: {str(e)}")
        return jsonify({'error': 'Failed to get bills'}), 500