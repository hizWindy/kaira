"""File storage abstraction module."""

from __future__ import annotations


class Storage:
    """Storage client abstraction (S3 / GCS / Local)."""

    def __init__(self, bucket: str = "default", backend: str = "local") -> None:
        self.bucket = bucket
        self.backend = backend

    async def upload(self, key: str, data: bytes) -> str:
        return f"{self.backend}://{self.bucket}/{key}"

    async def download(self, key: str) -> bytes:
        return b""


S3 = Storage
GCS = Storage

__all__ = ["GCS", "S3", "Storage"]
