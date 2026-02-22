"""
Firebase Storage — Medical Image Upload/Download
Handles storing and retrieving medical images (X-rays, scans) via Firebase Storage.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ImageStorage:
    """
    Medical image storage backed by Firebase Storage.
    Images are stored under: medical-images/{patient_id}/{filename}
    """
    
    def __init__(self):
        from src.config.firebase_config import get_storage_bucket
        self.bucket = get_storage_bucket()
        if self.bucket is None:
            raise RuntimeError("Firebase Storage bucket not available")
        logger.info("ImageStorage initialized with Firebase Storage")
    
    def upload_image(
        self,
        patient_id: str,
        image_path: str | Path,
        modality: str = "xray",
        description: str = ""
    ) -> dict:
        """
        Upload a medical image to Firebase Storage.
        
        Args:
            patient_id: Patient identifier
            image_path: Local path to the image file
            modality: Image modality (xray, ct, mri, ultrasound, etc.)
            description: Optional description
            
        Returns:
            Dict with storage URL and metadata
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Create storage path
        storage_path = f"medical-images/{patient_id}/{modality}/{image_path.name}"
        
        blob = self.bucket.blob(storage_path)
        
        # Detect content type
        suffix = image_path.suffix.lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".dcm": "application/dicom",
            ".dicom": "application/dicom",
        }
        content_type = content_types.get(suffix, "application/octet-stream")
        
        # Upload
        blob.upload_from_filename(str(image_path), content_type=content_type)
        
        # Make publicly accessible (for demo — in production use signed URLs)
        blob.make_public()
        
        logger.info("Uploaded image %s for patient %s", image_path.name, patient_id)
        
        return {
            "patient_id": patient_id,
            "storage_path": storage_path,
            "public_url": blob.public_url,
            "modality": modality,
            "description": description,
            "filename": image_path.name,
            "content_type": content_type,
            "size_bytes": blob.size
        }
    
    def download_image(self, storage_path: str, dest_dir: str | None = None) -> Path:
        """
        Download an image from Firebase Storage.
        
        Args:
            storage_path: Firebase Storage path (e.g., medical-images/P001/xray/scan.jpg)
            dest_dir: Optional destination directory. Uses temp dir if not specified.
            
        Returns:
            Local path to the downloaded file
        """
        blob = self.bucket.blob(storage_path)
        
        if not blob.exists():
            raise FileNotFoundError(f"Image not found in storage: {storage_path}")
        
        # Determine local path
        filename = Path(storage_path).name
        if dest_dir:
            local_path = Path(dest_dir) / filename
            local_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            local_path = Path(tempfile.mkdtemp()) / filename
        
        blob.download_to_filename(str(local_path))
        logger.info("Downloaded image %s", storage_path)
        
        return local_path
    
    def list_images(self, patient_id: str, modality: str | None = None) -> list[dict]:
        """
        List all images for a patient.
        
        Args:
            patient_id: Patient identifier
            modality: Optional filter by modality (xray, ct, mri, etc.)
            
        Returns:
            List of image metadata dicts
        """
        prefix = f"medical-images/{patient_id}/"
        if modality:
            prefix += f"{modality}/"
        
        blobs = self.bucket.list_blobs(prefix=prefix)
        
        images = []
        for blob in blobs:
            # Parse path to extract modality
            parts = blob.name.split("/")
            img_modality = parts[2] if len(parts) > 2 else "unknown"
            
            images.append({
                "storage_path": blob.name,
                "public_url": blob.public_url,
                "modality": img_modality,
                "filename": Path(blob.name).name,
                "size_bytes": blob.size,
                "updated": blob.updated.isoformat() if blob.updated else None
            })
        
        return images
    
    def delete_image(self, storage_path: str) -> bool:
        """Delete an image from storage."""
        blob = self.bucket.blob(storage_path)
        if blob.exists():
            blob.delete()
            logger.info("Deleted image %s", storage_path)
            return True
        return False


# Singleton
_image_storage: ImageStorage | None = None


def get_image_storage() -> ImageStorage | None:
    """Get the image storage singleton. Returns None if Firebase Storage is not configured."""
    global _image_storage
    if _image_storage is None:
        try:
            _image_storage = ImageStorage()
        except RuntimeError:
            return None
    return _image_storage
