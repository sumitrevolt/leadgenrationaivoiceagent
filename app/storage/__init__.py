# app/storage — S3-compatible object storage via MinIO (deploy/compose/docker-compose.addons.yml).
# Falls back to local ./data/ bind-mount when MinIO not configured (zero breaking change).
from .minio_client import StorageClient, get_storage

__all__ = ["StorageClient", "get_storage"]
