"""File storage adapters and factory (implements the FileStorage port).

``local`` writes to a mounted volume; ``s3`` targets any S3-compatible service
(MinIO/AWS). The factory picks the backend from settings. Reports and uploaded
import files are stored here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import settings
from app.domain.ports.storage import FileStorage


class LocalFileStorage:
    """Stores objects on the local filesystem under STORAGE_LOCAL_PATH."""

    def __init__(self, base_path: str | None = None) -> None:
        self._base = Path(base_path or settings.STORAGE_LOCAL_PATH)

    async def save(self, key: str, content: bytes, content_type: str) -> str:
        path = self._base / key
        await asyncio.to_thread(self._write, path, content)
        return str(path)

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def load(self, key: str) -> bytes:
        path = self._base / key
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._base / key
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))

    async def signed_url(self, key: str, expires_seconds: int = 3600) -> str:
        # Local storage has no signing; the API serves files via an auth'd route.
        return f"/api/v1/files/{key}"


class S3FileStorage:
    """Stores objects in an S3-compatible bucket (MinIO/AWS) via aioboto3."""

    def __init__(self) -> None:
        self._bucket = settings.S3_BUCKET

    def _client(self):
        import aioboto3  # imported lazily; optional dependency

        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
        )

    async def save(self, key: str, content: bytes, content_type: str) -> str:
        async with self._client() as s3:
            await s3.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)
        return f"s3://{self._bucket}/{key}"

    async def load(self, key: str) -> bytes:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self._bucket, Key=key)
            async with obj["Body"] as stream:
                return await stream.read()

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def signed_url(self, key: str, expires_seconds: int = 3600) -> str:
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )


def get_file_storage() -> FileStorage:
    """Return the configured file-storage backend."""
    if settings.STORAGE_BACKEND == "s3":
        return S3FileStorage()
    return LocalFileStorage()
