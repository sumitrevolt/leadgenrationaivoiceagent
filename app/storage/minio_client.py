"""minio_client.py — S3-compatible object storage via MinIO (deploy/compose/docker-compose.addons.yml).

Gap filled: app/marketing/ai_image.py currently saves AI-generated images to
`data/ai_images/` bind-mount (flat files, no S3 API, no presigned URLs, no CDN
pipeline, no lifecycle cleanup). This module provides a drop-in storage layer
with automatic fallback to local disk when MinIO is not configured.

ENV (all optional — unset = local disk fallback):
  MINIO_URL=http://minio:9000          (in-network from deploy/compose/docker-compose.addons.yml)
  MINIO_ROOT_USER=minioadmin
  MINIO_ROOT_PASSWORD=changeme_minio_secret
  MINIO_BUCKET=leadgen-assets          (public-read bucket for AI images)
  MINIO_PRIVATE_BUCKET=leadgen-private (private bucket for invoices/exports)
  MINIO_PUBLIC_URL=http://127.0.0.1:9000  (public base URL for presigned URLs)

Migration for ai_image.py:
  Instead of: Path("data/ai_images") / filename
  Use:        await get_storage().put("ai_images/" + filename, data, content_type="image/png")
              url = get_storage().public_url("ai_images/" + filename)

FAIL-OPEN: any MinIO error → falls back to local disk. Never raises.
Import-safe: boto3/aioboto3 missing → local-only mode (no container change needed).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from pathlib import Path
from typing import Optional

_log = logging.getLogger("storage.minio")

_DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _is_configured() -> bool:
    return bool(_env("MINIO_URL") and _env("MINIO_ROOT_USER") and _env("MINIO_ROOT_PASSWORD"))


class StorageClient:
    """Thin S3/MinIO wrapper with local-disk fallback.

    All methods are async and fail-open (never raise to caller).
    """

    def __init__(self):
        self._url = _env("MINIO_URL", "http://minio:9000")
        self._user = _env("MINIO_ROOT_USER", "minioadmin")
        self._pass = _env("MINIO_ROOT_PASSWORD", "")
        self._bucket = _env("MINIO_BUCKET", "leadgen-assets")
        self._private_bucket = _env("MINIO_PRIVATE_BUCKET", "leadgen-private")
        self._public_url = _env("MINIO_PUBLIC_URL", self._url)
        self._s3: object | None = None
        self._s3_init = False

    def _local_path(self, key: str) -> Path:
        p = _DATA_DIR / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _get_s3(self):
        """Lazy S3 client (boto3). Returns None if not configured / lib missing."""
        if self._s3_init:
            return self._s3
        self._s3_init = True
        if not _is_configured():
            return None
        try:
            import boto3
            from botocore.config import Config

            self._s3 = boto3.client(
                "s3",
                endpoint_url=self._url,
                aws_access_key_id=self._user,
                aws_secret_access_key=self._pass,
                config=Config(
                    signature_version="s3v4", connect_timeout=3, retries={"max_attempts": 2}
                ),
            )
            _log.info("MinIO storage client initialized: %s", self._url)
        except Exception as e:
            _log.info("MinIO unavailable (%s), using local disk fallback", e)
            self._s3 = None
        return self._s3

    async def put(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        private: bool = False,
    ) -> bool:
        """Upload bytes to MinIO (or local disk). Returns True on success."""
        bucket = self._private_bucket if private else self._bucket

        # Try MinIO first
        s3 = await asyncio.to_thread(self._get_s3)
        if s3 is not None:
            try:
                await asyncio.to_thread(
                    s3.put_object,
                    Bucket=bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
                _log.debug("MinIO put: s3://%s/%s (%d bytes)", bucket, key, len(data))
                return True
            except Exception as e:
                _log.warning("MinIO put failed (%s), falling back to disk: %s", key, e)

        # Local disk fallback
        try:
            path = self._local_path(key)
            await asyncio.to_thread(path.write_bytes, data)
            return True
        except Exception as e:
            _log.error("Storage put FAILED for %s: %s", key, e)
            return False

    async def get(self, key: str, private: bool = False) -> bytes | None:
        """Download bytes from MinIO (or local disk). Returns None if not found."""
        bucket = self._private_bucket if private else self._bucket

        s3 = await asyncio.to_thread(self._get_s3)
        if s3 is not None:
            try:
                resp = await asyncio.to_thread(s3.get_object, Bucket=bucket, Key=key)
                return resp["Body"].read()
            except Exception:
                pass

        # Local disk fallback
        try:
            path = self._local_path(key)
            if path.exists():
                return await asyncio.to_thread(path.read_bytes)
        except Exception:
            pass
        return None

    async def exists(self, key: str, private: bool = False) -> bool:
        """Check if object exists."""
        bucket = self._private_bucket if private else self._bucket
        s3 = await asyncio.to_thread(self._get_s3)
        if s3 is not None:
            try:
                await asyncio.to_thread(s3.head_object, Bucket=bucket, Key=key)
                return True
            except Exception:
                pass
        return self._local_path(key).exists()

    async def delete(self, key: str, private: bool = False) -> bool:
        """Delete object from MinIO and/or local disk."""
        bucket = self._private_bucket if private else self._bucket
        s3 = await asyncio.to_thread(self._get_s3)
        ok = False
        if s3 is not None:
            try:
                await asyncio.to_thread(s3.delete_object, Bucket=bucket, Key=key)
                ok = True
            except Exception:
                pass
        try:
            p = self._local_path(key)
            if p.exists():
                await asyncio.to_thread(p.unlink)
                ok = True
        except Exception:
            pass
        return ok

    def public_url(self, key: str) -> str:
        """Permanent public URL for a public-bucket object (no expiry)."""
        if _is_configured():
            return f"{self._public_url}/{self._bucket}/{key}"
        return f"/api/storage/file/{key}"  # local serve fallback

    async def presigned_url(
        self, key: str, expires: int = 3600, private: bool = False
    ) -> str | None:
        """Temporary presigned URL (private bucket or time-limited access)."""
        bucket = self._private_bucket if private else self._bucket
        s3 = await asyncio.to_thread(self._get_s3)
        if s3 is None:
            return None
        try:
            return await asyncio.to_thread(
                s3.generate_presigned_url,
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires,
            )
        except Exception as e:
            _log.warning("presigned_url failed for %s: %s", key, e)
            return None

    async def list_keys(self, prefix: str = "", private: bool = False) -> list[str]:
        """List object keys under a prefix."""
        bucket = self._private_bucket if private else self._bucket
        s3 = await asyncio.to_thread(self._get_s3)
        if s3 is not None:
            try:
                resp = await asyncio.to_thread(
                    s3.list_objects_v2, Bucket=bucket, Prefix=prefix, MaxKeys=1000
                )
                return [obj["Key"] for obj in resp.get("Contents", [])]
            except Exception:
                pass
        # Local fallback
        try:
            base = _DATA_DIR / prefix if prefix else _DATA_DIR
            if base.is_dir():
                return [str(p.relative_to(_DATA_DIR)) for p in base.rglob("*") if p.is_file()]
        except Exception:
            pass
        return []

    def using_minio(self) -> bool:
        """True if MinIO is configured (not local-disk fallback)."""
        return _is_configured()


# Module-level singleton (lazy-init, thread-safe enough for async)
_storage: StorageClient | None = None


def get_storage() -> StorageClient:
    """Get the singleton storage client. Always returns a usable instance."""
    global _storage
    if _storage is None:
        _storage = StorageClient()
    return _storage


__all__ = ["StorageClient", "get_storage"]
