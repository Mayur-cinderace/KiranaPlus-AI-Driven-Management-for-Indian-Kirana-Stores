import random
from datetime import datetime
from database import get_inventory_collection, is_db_connected
import logging
import re
from dateutil.parser import parse
import copy
from cachetools import TTLCache

# Cache for inventory items (5-minute TTL)
cache = TTLCache(maxsize=1, ttl=300)

def generate_unique_kirana_id(collection):
    """Generate a unique 6-digit kirana ID."""
    if not hasattr(collection, 'count_documents'):
        raise ValueError("Invalid collection provided")
    
    max_attempts = 100
    attempts = 0
    
    while attempts < max_attempts:
        kirana_id = random.randint(100000, 999999)
        if collection.count_documents({"kiranaId": kirana_id}) == 0:
            return kirana_id
        attempts += 1
    
    logging.warning("Failed to generate unique kirana ID after 100 attempts, using fallback")
    timestamp = int(datetime.utcnow().timestamp())
    random_suffix = random.randint(0, 999)
    return int(f"{timestamp % 1000000}{random_suffix:03d}"[-6:])

def validate_mobile_number(mobile):
    """Validate Indian mobile number format"""
    if not mobile or not isinstance(mobile, str):
        return False, "Mobile number is required"
    
    mobile = mobile.strip()
    pattern = r'^[6-9]\d{9}$'
    if not re.match(pattern, mobile):
        logging.debug(f"Invalid mobile number: {mobile}")
        return False, "Mobile number must be a 10-digit number starting with 6, 7, 8, or 9"
    
    return True, "Valid mobile number"

def validate_kirana_id(kirana_id):
    """Validate Kirana ID format"""
    if not kirana_id:
        return False, "Kirana ID is required"
    
    kirana_id = str(kirana_id).strip()
    if not kirana_id.isdigit() or len(kirana_id) != 6:
        logging.debug(f"Invalid kirana ID: {kirana_id}")
        return False, "Kirana ID must be a 6-digit number"
    
    kirana_id = int(kirana_id)
    if not (100000 <= kirana_id <= 999999):
        logging.debug(f"Invalid kirana ID range: {kirana_id}")
        return False, "Kirana ID must be between 100000 and 999999"
    
    return True, kirana_id

def get_inventory_items_from_db():
    """Fetch all inventory items from database for fuzzy matching"""
    if 'items' in cache:
        return cache['items']
    
    try:
        if not is_db_connected():
            logging.warning("No database connection for inventory matching")
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
        }).limit(1000))
        
        logging.info(f"Loaded {len(items)} inventory items for fuzzy matching")
        cache['items'] = items
        return items
        
    except Exception as e:
        logging.error(f"Error fetching inventory items: {e}")
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
    low_stock_items = 0
    out_of_stock_items = 0
    total_value = 0
    expiring_soon = 0
    current_date = datetime.utcnow()
    
    for item in items:
        if not all(key in item for key in ['stockQuantity', 'sellingPrice']):
            logging.warning(f"Missing required fields in item: {item.get('_id')}")
            continue
        
        stock = item.get('stockQuantity', 0)
        if stock < 10 and stock > 0:
            low_stock_items += 1
        elif stock == 0:
            out_of_stock_items += 1
        total_value += item.get('sellingPrice', 0) * stock
        
        if item.get('expiryDate'):
            try:
                expiry_date = parse(item['expiryDate']) if isinstance(item['expiryDate'], str) else item['expiryDate']
                days_to_expiry = (expiry_date - current_date).days
                if 0 <= days_to_expiry <= 30:
                    expiring_soon += 1
            except (ValueError, TypeError):
                continue
    
    avg_value = total_value / total_items if total_items > 0 else 0
    
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
    item = copy.deepcopy(item)
    
    if "_id" in item:
        item["_id"] = str(item["_id"])
    
    if "expiryDate" in item and isinstance(item["expiryDate"], datetime):
        item["expiryDate"] = item["expiryDate"].strftime("%Y-%m-%d")
    elif "expiryDate" in item and not isinstance(item["expiryDate"], str):
        item["expiryDate"] = ""  # Handle unexpected types
    
    if "createdAt" in item and isinstance(item["createdAt"], datetime):
        item["createdAt"] = item["createdAt"].isoformat()
    elif "createdAt" in item and not isinstance(item["createdAt"], str):
        item["createdAt"] = ""  # Handle unexpected types
    
    if "updatedAt" in item and isinstance(item["updatedAt"], datetime):
        item["updatedAt"] = item["updatedAt"].isoformat()
    elif "updatedAt" in item and not isinstance(item["updatedAt"], str):
        item["updatedAt"] = ""  # Handle unexpected types
    
    return item

def validate_price_logic(base_price, selling_price, mrp, gst):
    """Validate business logic for pricing"""
    TOLERANCE = 0.01
    
    if base_price <= 0:
        logging.debug(f"Price validation failed: Base price {base_price} <= 0")
        return False, "Base price must be greater than 0"
    
    if selling_price <= 0:
        logging.debug(f"Price validation failed: Selling price {selling_price} <= 0")
        return False, "Selling price must be greater than 0"
    
    if selling_price > mrp:
        logging.debug(f"Price validation failed: Selling price {selling_price} > MRP {mrp}")
        return False, "Selling price cannot be higher than MRP"
    
    if not (0 <= gst <= 100):
        logging.debug(f"Price validation failed: GST {gst} out of range")
        return False, "GST must be between 0 and 100"
    
    expected_selling_price = base_price + (base_price * gst / 100)
    if abs(selling_price - expected_selling_price) > TOLERANCE:
        logging.debug(f"Selling price mismatch: Expected {expected_selling_price:.2f}, Got {selling_price:.2f}")
        return False, f"Selling price mismatch. Expected: ₹{expected_selling_price:.2f}, Got: ₹{selling_price:.2f}"
    
    return True, "Price validation passed"