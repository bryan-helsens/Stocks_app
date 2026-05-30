"""Port for object/file storage (uploads, generated reports)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStorage(Protocol):
    """Stores and retrieves binary objects by key."""

    async def save(self, key: str, content: bytes, content_type: str) -> str:
        """Persist *content* under *key*; return a storage path/URI."""
        ...

    async def load(self, key: str) -> bytes:
        """Return the bytes stored under *key*."""
        ...

    async def delete(self, key: str) -> None: ...

    async def signed_url(self, key: str, expires_seconds: int = 3600) -> str:
        """Return a time-limited download URL for *key*."""
        ...
