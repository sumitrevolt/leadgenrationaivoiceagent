"""
Cloud Storage Utilities
Google Cloud Storage integration for file uploads
"""
import asyncio
from typing import Optional, Tuple
from io import BytesIO
import mimetypes

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def upload_to_gcs(
    bucket_name: str,
    file_path: str,
    content: bytes,
    content_type: str = "application/octet-stream"
) -> str:
    """
    Upload file to Google Cloud Storage
    
    Args:
        bucket_name: GCS bucket name
        file_path: Path within the bucket
        content: File content as bytes
        content_type: MIME type
        
    Returns:
        Public URL of uploaded file
    """
    try:
        from google.cloud import storage
        
        # Run in thread pool for async compatibility
        def _upload():
            client = storage.Client(project=settings.google_cloud_project_id)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            
            blob.upload_from_string(
                content,
                content_type=content_type
            )
            
            # Make publicly accessible (or use signed URLs for private)
            blob.make_public()
            
            return blob.public_url
        
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(None, _upload)
        
        logger.info(f"Uploaded to GCS: {bucket_name}/{file_path}")
        return url
        
    except ImportError:
        logger.warning("google-cloud-storage not installed")
        raise
    except Exception as e:
        logger.error(f"GCS upload failed: {e}")
        raise


async def download_from_gcs(
    bucket_name: str,
    file_path: str
) -> bytes:
    """
    Download file from Google Cloud Storage
    
    Args:
        bucket_name: GCS bucket name
        file_path: Path within the bucket
        
    Returns:
        File content as bytes
    """
    try:
        from google.cloud import storage
        
        def _download():
            client = storage.Client(project=settings.google_cloud_project_id)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            return blob.download_as_bytes()
        
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, _download)
        
        logger.info(f"Downloaded from GCS: {bucket_name}/{file_path}")
        return content
        
    except Exception as e:
        logger.error(f"GCS download failed: {e}")
        raise


async def delete_from_gcs(
    bucket_name: str,
    file_path: str
) -> bool:
    """
    Delete file from Google Cloud Storage
    
    Args:
        bucket_name: GCS bucket name
        file_path: Path within the bucket
        
    Returns:
        True if deleted
    """
    try:
        from google.cloud import storage
        
        def _delete():
            client = storage.Client(project=settings.google_cloud_project_id)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            blob.delete()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _delete)
        
        logger.info(f"Deleted from GCS: {bucket_name}/{file_path}")
        return True
        
    except Exception as e:
        logger.error(f"GCS delete failed: {e}")
        return False


async def generate_signed_url(
    bucket_name: str,
    file_path: str,
    expiration_minutes: int = 60
) -> str:
    """
    Generate a signed URL for private file access
    
    Args:
        bucket_name: GCS bucket name
        file_path: Path within the bucket
        expiration_minutes: URL validity duration
        
    Returns:
        Signed URL
    """
    try:
        from google.cloud import storage
        from datetime import timedelta
        
        def _generate():
            client = storage.Client(project=settings.google_cloud_project_id)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(file_path)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET"
            )
            return url
        
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(None, _generate)
        
        return url
        
    except Exception as e:
        logger.error(f"Signed URL generation failed: {e}")
        raise


async def generate_thumbnail(
    image_content: bytes,
    size: Tuple[int, int] = (150, 150),
    quality: int = 85
) -> bytes:
    """
    Generate thumbnail from image
    
    Args:
        image_content: Original image bytes
        size: Thumbnail dimensions (width, height)
        quality: JPEG quality (1-100)
        
    Returns:
        Thumbnail image bytes
    """
    try:
        from PIL import Image
        
        def _generate():
            # Open image
            img = Image.open(BytesIO(image_content))
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                img = background
            
            # Create thumbnail (maintains aspect ratio)
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            output.seek(0)
            
            return output.read()
        
        loop = asyncio.get_event_loop()
        thumbnail = await loop.run_in_executor(None, _generate)
        
        return thumbnail
        
    except ImportError:
        logger.warning("Pillow not installed, returning original")
        return image_content
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")
        raise


async def list_files_in_bucket(
    bucket_name: str,
    prefix: str = "",
    max_results: int = 100
) -> list:
    """
    List files in a GCS bucket
    
    Args:
        bucket_name: GCS bucket name
        prefix: Filter by prefix
        max_results: Maximum files to return
        
    Returns:
        List of file info dicts
    """
    try:
        from google.cloud import storage
        
        def _list():
            client = storage.Client(project=settings.google_cloud_project_id)
            bucket = client.bucket(bucket_name)
            
            blobs = bucket.list_blobs(prefix=prefix, max_results=max_results)
            
            files = []
            for blob in blobs:
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "content_type": blob.content_type,
                    "created": blob.time_created.isoformat() if blob.time_created else None,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "public_url": blob.public_url
                })
            
            return files
        
        loop = asyncio.get_event_loop()
        files = await loop.run_in_executor(None, _list)
        
        return files
        
    except Exception as e:
        logger.error(f"List files failed: {e}")
        return []


def create_bucket_if_not_exists(bucket_name: str, location: str = "asia-south1") -> bool:
    """
    Create a GCS bucket if it doesn't exist
    
    Args:
        bucket_name: Bucket name to create
        location: GCS location
        
    Returns:
        True if created or exists
    """
    try:
        from google.cloud import storage
        from google.cloud.exceptions import Conflict
        
        client = storage.Client(project=settings.google_cloud_project_id)
        
        try:
            bucket = client.create_bucket(bucket_name, location=location)
            logger.info(f"Created bucket: {bucket_name}")
            return True
        except Conflict:
            # Bucket already exists
            logger.info(f"Bucket already exists: {bucket_name}")
            return True
            
    except Exception as e:
        logger.error(f"Create bucket failed: {e}")
        return False
