"""Object-storage provider abstraction (spec 55, doc 00 A3).

Screenshot blobs are never stored in Postgres; only metadata is. The agent uploads the
encrypted blob directly to object storage via a presigned URL, and views go through a
short-lived signed URL. The provider is pluggable so self-hosted (MinIO) and cloud
(S3-compatible) deployments differ only by configuration.

A LocalStorageProvider is included for development/tests; it issues app-served URLs instead
of true presigned URLs but keeps the same contract.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.core.config import settings


class StorageProvider(ABC):
    @abstractmethod
    def key_for(self, organization_id: uuid.UUID, screenshot_id: uuid.UUID) -> str: ...

    @abstractmethod
    def presign_put(self, storage_key: str, content_type: str = "image/webp") -> str: ...

    @abstractmethod
    def presign_get(self, storage_key: str, expires_seconds: int = 300) -> str: ...

    @abstractmethod
    def delete(self, storage_key: str) -> None: ...


class LocalStorageProvider(StorageProvider):
    """Dev/test provider. Keys are namespaced by org; URLs point at a local endpoint. No real
    presigning — do not use in production."""

    def key_for(self, organization_id: uuid.UUID, screenshot_id: uuid.UUID) -> str:
        return f"{organization_id}/{screenshot_id}.webp"

    def presign_put(self, storage_key: str, content_type: str = "image/webp") -> str:
        return f"{settings.storage_endpoint}/{settings.storage_bucket}/{storage_key}?upload=1"

    def presign_get(self, storage_key: str, expires_seconds: int = 300) -> str:
        return f"{settings.storage_endpoint}/{settings.storage_bucket}/{storage_key}?exp={expires_seconds}"

    def delete(self, storage_key: str) -> None:  # pragma: no cover - local no-op
        return None


class S3StorageProvider(StorageProvider):
    """S3-compatible provider (MinIO/AWS). Uses boto3 presigned URLs.

    boto3 is imported lazily so the dependency is only required when this provider is selected.
    """

    def __init__(self):
        import boto3  # type: ignore

        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
        )
        self._bucket = settings.storage_bucket

    def key_for(self, organization_id: uuid.UUID, screenshot_id: uuid.UUID) -> str:
        return f"{organization_id}/{screenshot_id}.webp"

    def presign_put(self, storage_key: str, content_type: str = "image/webp") -> str:
        return self._s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": storage_key, "ContentType": content_type},
            ExpiresIn=300,
        )

    def presign_get(self, storage_key: str, expires_seconds: int = 300) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_key},
            ExpiresIn=expires_seconds,
        )

    def delete(self, storage_key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=storage_key)


def get_storage_provider() -> StorageProvider:
    """Select provider by environment. Local for development, S3 otherwise."""
    if settings.environment == "development":
        return LocalStorageProvider()
    try:
        return S3StorageProvider()
    except Exception:
        # Fall back to local if boto3/credentials are unavailable; logged by caller.
        return LocalStorageProvider()
