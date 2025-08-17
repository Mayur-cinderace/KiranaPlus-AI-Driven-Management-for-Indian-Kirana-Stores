from pymongo import MongoClient
from config import Config
import logging

# Global database client
client = None

def init_db():
    """Initialize MongoDB connection"""
    global client
    try:
        client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        client.admin.command('ping')
        print("✅ MongoDB connected successfully")
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        logging.error(f"MongoDB connection failed: {e}")
        client = None
        return False

def get_db_client():
    """Get the database client"""
    return client

def get_collection(db_name, collection_name):
    """Get a specific collection"""
    if not client:
        raise Exception("Database not connected")
    return client[db_name][collection_name]

def get_user_collection():
    """Get user signups collection"""
    return get_collection(Config.USER_DB_NAME, "signups")

def get_retailer_collection():
    """Get retailer signups collection"""
    return get_collection(Config.RETAILER_DB_NAME, "signups")

def get_inventory_collection():
    """Get inventory items collection"""
    return get_collection(Config.INVENTORY_DB_NAME, "items")

def is_db_connected():
    """Check if database is connected"""
    return client is not None