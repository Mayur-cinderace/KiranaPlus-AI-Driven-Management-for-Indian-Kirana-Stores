from flask import Blueprint, jsonify
from datetime import datetime
from database import is_db_connected
from ocr_service import get_ocr_reader
from config import Config

health_bp = Blueprint('health', __name__, url_prefix='/api')

@health_bp.route('/health', methods=['GET'])
def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Check OCR status
        ocr_reader = get_ocr_reader()
        ocr_status = "initialized" if ocr_reader is not None else "failed"
        
        # Check database status
        db_status = "connected" if is_db_connected() else "disconnected"
        
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
                }
            },
            'port': Config.PORT
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500