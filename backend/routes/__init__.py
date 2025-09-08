# __init__.py
from datetime import datetime
from database import is_db_connected
from ocr_service import get_ocr_reader
from config import Config

# Move this to a utility function if needed, but don’t create a blueprint here
def health_check():
    try:
        ocr_reader = get_ocr_reader()
        ocr_status = "initialized" if ocr_reader is not None else "failed"
        db_status = "connected" if is_db_connected() else "disconnected"
        return {
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
        }, 200
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500