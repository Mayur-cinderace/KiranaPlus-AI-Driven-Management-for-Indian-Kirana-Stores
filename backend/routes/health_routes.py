from flask import Blueprint, jsonify
from datetime import datetime
from database import is_db_connected
from ocr_service import get_ocr_reader, get_gemini_model
from config import Config

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Check OCR status
        ocr_reader = get_ocr_reader()
        ocr_status = "initialized" if ocr_reader is not None else "failed"
        
        # Check database status
        db_status = "connected" if is_db_connected() else "disconnected"
        
        # Check Gemini API status
        gemini_model = get_gemini_model()
        gemini_status = "configured" if gemini_model is not None else "not_configured"
        
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'Combined Kirana API Server',
            'components': {
                'ocr': {
                    'status': ocr_status,
                    'gpu_enabled': False,
                    'backend': 'EasyOCR'
                },
                'database': {
                    'status': db_status,
                    'mongo_uri_configured': bool(Config.MONGO_URI)
                },
                'gemini_api': {
                    'status': gemini_status
                }
            },
            'port': Config.PORT
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500