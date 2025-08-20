import os
from dotenv import load_dotenv

load_dotenv() 
class Config:
    """Application configuration"""
    
    # Server configuration
    PORT = int(os.getenv('PORT', 49285))  # Server listening port
    DEBUG = bool(os.getenv('DEBUG', True))  # Debug mode (False in production)
    
    # MongoDB configuration
    MONGO_URI = os.getenv('MONGO_URI')  # Required: MongoDB connection string
    
    # Gemini API configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')  # Required: Gemini API key
    
    # OCR configuration
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff'}  # Allowed file types for OCR/uploads
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max file size in bytes
    
    # Upload configuration
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')  # Absolute path for uploads
    
    # Database names
    USER_DB_NAME = "user_signups"  # User signups database
    RETAILER_DB_NAME = "retailer_signups"  # Retailer signups database
    INVENTORY_DB_NAME = "kirana_inventory"  # Inventory database
    
    # Business logic constants
    LOW_STOCK_THRESHOLD = 10  # Threshold for low stock alerts
    EXPIRY_WARNING_DAYS = 30  # Days before expiry to trigger warnings
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())  # For sessions/JWT

# Environment-specific configs
class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

# Usage in app.py: config = DevelopmentConfig() if os.getenv('FLASK_ENV') == 'development' else ProductionConfig()