import os


class Config:
    """Application configuration"""
    
    # Server configuration
    PORT = 49285
    DEBUG = True
    
    # MongoDB configuration
    MONGO_URI = "mongodb+srv://Kirana_1:kiranadb@Cluster0.3autbfc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    
    # Gemini API configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    
    # OCR configuration
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    
    # Upload configuration
    UPLOAD_FOLDER = 'uploads'
    
    # Database names
    USER_DB_NAME = "user_signups"
    RETAILER_DB_NAME = "retailer_signups" 
    INVENTORY_DB_NAME = "kirana_inventory"
    
    # Business logic constants
    LOW_STOCK_THRESHOLD = 10
    EXPIRY_WARNING_DAYS = 30