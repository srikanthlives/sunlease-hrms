"""Storage abstraction: local filesystem or Cloudflare R2 (S3-compatible),
ported from the sibling sunlease-expms project's app/services/storage.py.

Adapted to HRMS's existing convention (unlike expms, which auto-generates a
project/category/year/month/week path): callers here already build the exact
relative object_key HRMS has always used (see document_service.py's
_employee_upload_dir/_candidate_upload_dir - company/employee-number/doctype,
candidates/reference-number/doctype, etc.) and stored in the DB, so this just
needs to save/read/delete that exact key through whichever backend is
configured (HRMS_STORAGE_TYPE) - swapping backends never changes existing
object_key values or requires a data migration.
"""
import os
from abc import ABC, abstractmethod

from fastapi import HTTPException, status

from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save(self, relative_key: str, content: bytes) -> None:
        """Write `content` at `relative_key` (creating any needed folders)."""

    @abstractmethod
    def read(self, relative_key: str) -> bytes:
        """Return the file's bytes, or 404 if it doesn't exist."""

    @abstractmethod
    def delete(self, relative_key: str) -> None:
        """Remove the file if it exists; a no-op otherwise."""

    @abstractmethod
    def exists(self, relative_key: str) -> bool:
        pass


class LocalStorageBackend(StorageBackend):
    """Store files on local disk under settings.UPLOAD_DIR - the default,
    and what every HRMS deployment has used until now."""

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    def _path(self, relative_key: str) -> str:
        return os.path.join(self.upload_dir, relative_key)

    def save(self, relative_key: str, content: bytes) -> None:
        path = self._path(relative_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    def read(self, relative_key: str) -> bytes:
        path = self._path(relative_key)
        if not os.path.exists(path):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
        with open(path, "rb") as f:
            return f.read()

    def delete(self, relative_key: str) -> None:
        path = self._path(relative_key)
        if os.path.exists(path):
            os.remove(path)

    def exists(self, relative_key: str) -> bool:
        return os.path.exists(self._path(relative_key))


class R2StorageBackend(StorageBackend):
    """Store files in a Cloudflare R2 bucket (S3-compatible API), under a
    fixed root prefix (default 'HRMS') so every upload lands in one
    identifiable place in the bucket - same idea as sunlease-expms's
    R2StorageBackend, minus its auto-generated path layout (see module
    docstring)."""

    def __init__(self):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            print("[ERROR][STORAGE] boto3 is not installed - cannot use R2 storage (HRMS_STORAGE_TYPE=r2).")
            raise ImportError("boto3 is required for R2 storage. Install with: pip install boto3")

        missing = []
        if not settings.R2_ACCOUNT_ID and not settings.R2_ENDPOINT_URL:
            missing.append("HRMS_R2_ACCOUNT_ID (or HRMS_R2_ENDPOINT_URL)")
        if not settings.R2_ACCESS_KEY_ID:
            missing.append("HRMS_R2_ACCESS_KEY_ID")
        if not settings.R2_SECRET_ACCESS_KEY:
            missing.append("HRMS_R2_SECRET_ACCESS_KEY")
        if not settings.R2_BUCKET_NAME:
            missing.append("HRMS_R2_BUCKET_NAME")
        if missing:
            print(f"[ERROR][STORAGE] R2 storage is misconfigured - missing: {', '.join(missing)}. Every document upload/download will fail until this is set.")
            raise ValueError(f"Missing required R2 setting(s) for HRMS_STORAGE_TYPE=r2: {', '.join(missing)}")

        endpoint_url = settings.R2_ENDPOINT_URL or f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        print(f"[INFO][STORAGE] Using Cloudflare R2 storage: bucket='{settings.R2_BUCKET_NAME}', prefix='{settings.R2_PREFIX}', endpoint='{endpoint_url}'")

        self.bucket = settings.R2_BUCKET_NAME
        self.prefix = settings.R2_PREFIX.strip("/")
        try:
            self.client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                config=BotoConfig(signature_version="s3v4"),
                region_name="auto",
            )
        except Exception as exc:
            print(f"[ERROR][STORAGE] Failed to create the R2 client (endpoint='{endpoint_url}', bucket='{self.bucket}'): {exc}")
            raise

    def _key(self, relative_key: str) -> str:
        relative_key = relative_key.replace(os.sep, "/")
        return f"{self.prefix}/{relative_key}" if self.prefix else relative_key

    def save(self, relative_key: str, content: bytes) -> None:
        key = self._key(relative_key)
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=content)
        except Exception as exc:
            print(f"[ERROR][STORAGE] R2 upload failed (bucket='{self.bucket}', key='{key}', {len(content)} bytes): {exc}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not upload file to storage: {exc}")

    def read(self, relative_key: str) -> bytes:
        key = self._key(relative_key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except self.client.exceptions.NoSuchKey:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
            if error_code in ("NoSuchKey", "404"):
                # A genuinely missing file is an expected, everyday case (a
                # stale DB row, a file removed out-of-band) - not an error to
                # alarm on.
                raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
            print(f"[ERROR][STORAGE] R2 download failed (bucket='{self.bucket}', key='{key}'): {exc}")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not read file from storage: {exc}")

    def delete(self, relative_key: str) -> None:
        key = self._key(relative_key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            # Not re-raised: callers treat delete as best-effort (e.g.
            # cleaning up a draft being discarded) - but a real problem
            # (auth/network/bucket misconfig) must still show up in the logs
            # instead of silently looking like a successful delete.
            print(f"[ERROR][STORAGE] R2 delete failed (bucket='{self.bucket}', key='{key}') - the file may still exist in R2: {exc}")

    def exists(self, relative_key: str) -> bool:
        key = self._key(relative_key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
            if error_code != "404":
                # A 404 just means "doesn't exist" - the normal, expected
                # result for this check. Anything else (auth/network/bucket
                # misconfig) is a real problem and must be visible in the logs.
                print(f"[ERROR][STORAGE] R2 exists-check failed (bucket='{self.bucket}', key='{key}'): {exc}")
            return False


_storage_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """The configured storage backend (singleton)."""
    global _storage_backend
    if _storage_backend is None:
        _storage_backend = R2StorageBackend() if settings.STORAGE_TYPE == "r2" else LocalStorageBackend()
    return _storage_backend
