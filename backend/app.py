from flask import Flask
from flask_cors import CORS
from config import Config
from database import init_db
from ocr_service import init_ocr
from routes.health_routes import health_bp
from routes.ocr_routes import ocr_bp
from routes.auth_routes import auth_bp
from routes.inventory_routes import inventory_bp
from routes.search_routes import search_bp
from routes.bill_routes import bill_bp
import logging
import os
from logging.handlers import RotatingFileHandler

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(Config)
    
    # Configure CORS
    CORS(app, resources={
        r"/health": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["GET", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        },
        r"/upload-receipt": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        },
        r"/save-receipt-items": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        },
        r"/get-all-items": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["GET", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        },
        r"/add-item": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        },
        r"/generate-bill": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        },
        r"/api/*": {
            "origins": [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://localhost:3000"
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Accept"]
        }
    }, supports_credentials=False)
    
    # Configure logging
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, 'flask_errors.log'),
        maxBytes=1000000,
        backupCount=5
    )
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            handler,
            logging.StreamHandler()
        ]
    )
    
    # Create uploads directory if it doesn't exist
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    # Initialize database connection
    if not init_db():
        logging.error("Failed to initialize database")
        raise RuntimeError("Database initialization failed")
    
    # Initialize OCR service
    try:
        init_ocr()
    except Exception as e:
        logging.error(f"Failed to initialize OCR service: {str(e)}")
        raise RuntimeError("OCR initialization failed")
    
    # Register blueprints
    try:
        app.register_blueprint(health_bp)
        app.register_blueprint(ocr_bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(inventory_bp)
        app.register_blueprint(search_bp)
        app.register_blueprint(bill_bp)
    except Exception as e:
        logging.error(f"Failed to register blueprint: {str(e)}")
        raise
    
    # Error handlers
    @app.errorhandler(400)
    def bad_request(error):
        return {"error": "Bad request"}, 400

    @app.errorhandler(401)
    def unauthorized(error):
        return {"error": "Unauthorized"}, 401

    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Endpoint not found"}, 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return {"error": "Method not allowed"}, 405

    @app.errorhandler(500)
    def internal_error(error):
        logging.error(f"Internal server error: {str(error)}")
        return {"error": "Internal server error"}, 500
    
    return app

if __name__ == "__main__":
    if os.getenv('FLASK_ENV') == 'production':
        raise RuntimeError("Debug mode should not be used in production")
    app = create_app()
    print("🚀 Starting Combined Kirana API Server...")
    print(f"📡 Server will be available at: http://localhost:{Config.PORT}")
    print(f"🔗 Health check: http://localhost:{Config.PORT}/health")
    app.run(port=Config.PORT, debug=Config.DEBUG)