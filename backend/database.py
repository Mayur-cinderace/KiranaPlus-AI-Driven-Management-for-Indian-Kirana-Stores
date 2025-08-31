from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from config import Config
import logging
import time

# Global database client
client = None

def init_db():
    """Initialize MongoDB connection with retries"""
    global client
    if not Config.MONGO_URI:
        logging.error("MONGO_URI is not set")
        raise ValueError("MONGO_URI is required")
    
    retries = 3
    for attempt in range(retries):
        try:
            client = MongoClient(Config.MONGO_URI)
            client.admin.command('ping')
            print("✅ MongoDB connected successfully")
            return True
        except ConnectionFailure as e:
            logging.error(f"MongoDB connection attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)  # Wait before retrying
            continue
    print("❌ MongoDB connection failed after retries")
    client = None
    return False

def get_db_client():
    """Get the database client"""
    return client

def get_db():
    """
    Get the main database for insights and analytics
    This function is required by the insights module
    """
    if client is None:
        logging.error("Database client is None")
        raise Exception("Database not connected")
    
    # Return the inventory database which contains bills and items
    return client[Config.INVENTORY_DB_NAME]

def get_collection(db_name, collection_name):
    """Get a specific collection"""
    if client is None:
        logging.error("Database client is None")
        raise Exception("Database not connected")
    
    if not db_name or not collection_name:
        raise ValueError("Database name and collection name are required")
    
    try:
        database = client[db_name]
        collection = database[collection_name]
        
        # Optional: Check if collection exists (warning only)
        existing_collections = database.list_collection_names()
        if collection_name not in existing_collections:
            logging.warning(f"Collection {collection_name} in {db_name} does not exist, will be created on first write")
        
        return collection
    except Exception as e:
        logging.error(f"Error accessing collection {collection_name} in database {db_name}: {str(e)}")
        raise

def get_user_collection():
    """Get user signups collection"""
    try:
        return get_collection(Config.USER_DB_NAME, "signups")
    except Exception as e:
        logging.error(f"Error getting user collection: {str(e)}")
        return None

def get_retailer_collection():
    """Get retailer signups collection"""
    try:
        return get_collection(Config.RETAILER_DB_NAME, "signups")
    except Exception as e:
        logging.error(f"Error getting retailer collection: {str(e)}")
        return None

def get_inventory_collection():
    """Get inventory items collection"""
    try:
        return get_collection(Config.INVENTORY_DB_NAME, "items")
    except Exception as e:
        logging.error(f"Error getting inventory collection: {str(e)}")
        return None

def get_bills_collection():
    """
    Get the bills collection from MongoDB
    Returns the bills collection object
    """
    try:
        # Store bills in the same database as inventory for simplicity
        return get_collection(Config.INVENTORY_DB_NAME, "bills")
    except Exception as e:
        logging.error(f"Error getting bills collection: {str(e)}")
        return None
    
def get_receipts_collection():
    """
    Get the receipts collection from MongoDB
    Returns the receipts collection object
    """
    try:
        # Store receipts in the same database as inventory for simplicity
        return get_collection(Config.INVENTORY_DB_NAME, "receipts")
    except Exception as e:
        logging.error(f"Error getting receipts collection: {str(e)}")
        return None

def is_db_connected():
    """Check if database is connected and active"""
    if client is None:
        return False
    try:
        client.admin.command('ping')
        return True
    except Exception:
        return False

def close_db_connection():
    """Close the database connection"""
    global client
    if client is not None:
        try:
            client.close()
            client = None
            logging.info("Database connection closed")
        except Exception as e:
            logging.error(f"Error closing database connection: {e}")

# Debug function (remove in production)
def debug_database_status():
    """Debug function to check database status - remove in production"""
    print(f"Client type: {type(client)}")
    print(f"Client is None: {client is None}")
    
    print(f"INVENTORY_DB_NAME: {Config.INVENTORY_DB_NAME}")
    print(f"USER_DB_NAME: {Config.USER_DB_NAME}")
    print(f"RETAILER_DB_NAME: {Config.RETAILER_DB_NAME}")
    
    if client is not None:
        try:
            print(f"Database names: {client.list_database_names()}")
            
            # Test getting inventory collection
            inv_collection = get_inventory_collection()
            print(f"Inventory collection type: {type(inv_collection)}")
            
            # Test getting bills collection
            bills_collection = get_bills_collection()
            print(f"Bills collection type: {type(bills_collection)}")
            
            # Test the get_db function
            main_db = get_db()
            print(f"Main database type: {type(main_db)}")
            print(f"Main database collections: {main_db.list_collection_names()}")
            
        except Exception as e:
            print(f"Error during debug: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Client is None - database not connected")