from flask import Flask
from flask_cors import CORS
from config import Config
from database import init_db
from ocr_service import init_ocr
from routes.health_routes import health_bp
from routes.ocr_routes import ocr_bp
from routes.auth_routes import auth_bp
from routes.inventory_routes import inventory_bp
import logging
import os


def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Configure CORS
    CORS(app, 
         origins=["http://localhost:*", "http://127.0.0.1:*", "file://*", "*"],
         methods=["GET", "POST", "PUT", "DELETE"],
         allow_headers=["Content-Type", "Accept"])
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('flask_errors.log'),
            logging.StreamHandler()
        ]
    )
    
    # Create uploads directory if it doesn't exist
    os.makedirs('uploads', exist_ok=True)
    
    # Initialize database connection
    init_db()
    
    # Initialize OCR service
    init_ocr()
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(ocr_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(inventory_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Endpoint not found"}, 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return {"error": "Method not allowed"}, 405

    @app.errorhandler(500)
    def internal_error(error):
        return {"error": "Internal server error"}, 500
    
    return app


if __name__ == "__main__":
    app = create_app()
    print("🚀 Starting Combined Kirana API Server...")
    print(f"📡 Server will be available at: http://localhost:{Config.PORT}")
    print(f"🔗 Health check: http://localhost:{Config.PORT}/health")
    app.run(port=Config.PORT, debug=Config.DEBUG)