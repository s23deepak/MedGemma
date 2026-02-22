"""
Firebase Admin SDK initialization.
Provides Firestore client and Storage bucket for the application.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy-loaded singletons
_firestore_client = None
_storage_bucket = None
_initialized = False


def _init_firebase():
    """Initialize Firebase Admin SDK from service account key."""
    global _initialized
    if _initialized:
        return
    
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("firebase-admin not installed. Run: uv add firebase-admin")
        _initialized = True
        return
    
    # Already initialized by another module?
    if firebase_admin._apps:
        _initialized = True
        return
    
    # Find the service account key
    key_path = os.environ.get("FIREBASE_KEY_PATH", "firebase-key.json")
    
    # Try relative to project root
    project_root = Path(__file__).parent.parent.parent
    full_path = project_root / key_path
    
    if not full_path.exists():
        # Try absolute path
        full_path = Path(key_path)
    
    if not full_path.exists():
        logger.info("Firebase key not found at %s — Firebase features disabled", key_path)
        _initialized = True
        return
    
    try:
        cred = credentials.Certificate(str(full_path))
        firebase_admin.initialize_app(cred, {
            "storageBucket": _get_bucket_name(full_path)
        })
        logger.info("Firebase initialized from %s", full_path.name)
        _initialized = True
    except Exception as e:
        logger.warning("Firebase initialization failed: %s", e)
        _initialized = True


def _get_bucket_name(key_path: Path) -> str:
    """Extract the default storage bucket from the service account key."""
    try:
        with open(key_path) as f:
            key_data = json.load(f)
        project_id = key_data.get("project_id", "")
        return f"{project_id}.firebasestorage.app"
    except Exception:
        return ""


def get_firestore_client():
    """Get the Firestore client. Returns None if Firebase is not configured."""
    global _firestore_client
    _init_firebase()
    
    if _firestore_client is None:
        try:
            from firebase_admin import firestore
            _firestore_client = firestore.client()
        except Exception:
            return None
    
    return _firestore_client


def get_storage_bucket():
    """Get the Firebase Storage bucket. Returns None if not configured."""
    global _storage_bucket
    _init_firebase()
    
    if _storage_bucket is None:
        try:
            from firebase_admin import storage
            _storage_bucket = storage.bucket()
        except Exception:
            return None
    
    return _storage_bucket


def is_firebase_available() -> bool:
    """Check if Firebase is configured and available."""
    return get_firestore_client() is not None
