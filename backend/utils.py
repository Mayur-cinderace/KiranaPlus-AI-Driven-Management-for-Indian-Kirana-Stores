import random
from datetime import datetime
from database import get_inventory_collection, is_db_connected

def generate_unique_kirana_id(collection):
    """Generate a unique 6-digit kirana ID."""
    max_attempts = 100  # Prevent infinite loop
    attempts = 0
    
    while attempts < max_attempts:
        kirana_id = random.randint(100000, 999999)
        if collection.count_documents({"kiranaId": kirana_id}) == 0:
            return kirana_id
        attempts += 1
    
    # If we can't find a unique ID, use timestamp-based approach
    timestamp = int(datetime.utcnow().timestamp())
    return int(str(timestamp)[-6:])

def validate_mobile_number(mobile):
    """Validate Indian mobile number format"""
    if not mobile or not isinstance(mobile, str):
        return False, "Mobile number is required"
    
    mobile = mobile.strip()
    
    if not mobile.isdigit():
        return False, "Mobile number should contain only digits"
    
    if len(mobile) != 10:
        return False, "Mobile number should be exactly 10 digits"
    
    if not mobile.startswith(('6', '7', '8', '9')):
        return False, "Mobile number should start with 6, 7, 8, or 9"
    
    return True, "Valid mobile number"

def validate_kirana_id(kirana_id):
    """Validate Kirana ID format"""
    if not kirana_id:
        return False, "Kirana ID is required"
    
    try:
        kirana_id = int(kirana_id)
        if not (100000 <= kirana_id <= 999999):
            return False, "Kirana ID must be a 6-digit number"
        return True, kirana_id
    except (ValueError, TypeError):
        return False, "Invalid Kirana ID format"

def get_inventory_items_from_db():
    """Fetch all inventory items from database for fuzzy matching"""
    try:
        if not is_db_connected():
            print("Warning: No database connection for inventory matching")
            return []
            
        collection = get_inventory_collection()
        
        items = list(collection.find({}, {
            'itemName': 1, 
            'brand': 1, 
            'category': 1, 
            'itemId': 1,
            'unitSize': 1,
            'sellingPrice': 1,
            'mrp': 1
        }))
        
        print(f"Loaded {len(items)} inventory items for fuzzy matching")
        return items
        
    except Exception as e:
        print(f"Error fetching inventory items: {e}")
        return []

def calculate_inventory_summary(items):
    """Calculate inventory summary statistics"""
    if not items:
        return {
            'totalItems': 0,
            'lowStockItems': 0,
            'outOfStockItems': 0,
            'totalValue': 0,
            'avgValue': 0,
            'expiringSoonItems': 0
        }
    
    total_items = len(items)
    low_stock_items = len([item for item in items if item.get('stockQuantity', 0) < 10 and item.get('stockQuantity', 0) > 0])
    out_of_stock_items = len([item for item in items if item.get('stockQuantity', 0) == 0])
    
    # Calculate total inventory value
    total_value = sum([
        item.get('sellingPrice', 0) * item.get('stockQuantity', 0) 
        for item in items
    ])
    
    avg_value = total_value / total_items if total_items > 0 else 0
    
    # Check for items expiring within 30 days
    current_date = datetime.now()
    expiring_soon = 0
    
    for item in items:
        if item.get('expiryDate'):
            try:
                if isinstance(item['expiryDate'], str):
                    expiry_date = datetime.strptime(item['expiryDate'], '%Y-%m-%d')
                else:
                    expiry_date = item['expiryDate']
                days_to_expiry = (expiry_date - current_date).days
                if 0 <= days_to_expiry <= 30:
                    expiring_soon += 1
            except:
                pass
    
    return {
        'totalItems': total_items,
        'lowStockItems': low_stock_items,
        'outOfStockItems': out_of_stock_items,
        'totalValue': round(total_value, 2),
        'avgValue': round(avg_value, 2),
        'expiringSoonItems': expiring_soon
    }

def convert_item_for_json(item):
    """Convert database item for JSON serialization"""
    if "_id" in item:
        item["_id"] = str(item["_id"])
    
    # Convert datetime back to string for JSON serialization
    if "expiryDate" in item and not isinstance(item["expiryDate"], str):
        item["expiryDate"] = item["expiryDate"].strftime("%Y-%m-%d")
    if "createdAt" in item and not isinstance(item["createdAt"], str):
        item["createdAt"] = item["createdAt"].isoformat()
    if "updatedAt" in item and not isinstance(item["updatedAt"], str):
        item["updatedAt"] = item["updatedAt"].isoformat()
    
    return item

def validate_price_logic(base_price, selling_price, mrp, gst):
    """Validate business logic for pricing"""
    if base_price <= 0:
        return False, "Base price must be greater than 0"
    
    if selling_price <= 0:
        return False, "Selling price must be greater than 0"
    
    if selling_price > mrp:
        return False, "Selling price cannot be higher than MRP"
    
    if not (0 <= gst <= 100):
        return False, "GST must be between 0 and 100"
    
    # Validate that selling price calculation is correct
    expected_selling_price = base_price + (base_price * gst / 100)
    if abs(selling_price - expected_selling_price) > 0.01:  # Allow small floating point differences
        return False, f"Selling price mismatch. Expected: ₹{expected_selling_price:.2f}, Got: ₹{selling_price:.2f}"
    
    return True, "Price validation passed"