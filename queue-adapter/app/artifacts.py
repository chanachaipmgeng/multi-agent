"""Optional MinIO / S3 artifact uploads (design D3.7)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger("emaw.adapter.artifacts")


class ArtifactStore:
    """Minimal S3-compatible PUT via HTTP (no boto3 dependency)."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def put_text(
        self, *, project: str, task_id: str, name: str, body: str, content_type: str = "text/plain"
    ) -> str | None:
        if not self.enabled or not body:
            return None
        key = f"{project}/{task_id}/{name}"
        url = f"{self.endpoint}/{self.bucket}/{key}"
        # Prefer path-style PUT; MinIO accepts unsigned PUT when anonymous write
        # is enabled, but we send basic AWS SigV4-lite via query-style for simplicity
        # using MinIO's common ACCESS_KEY/SECRET as Basic auth fallback for local.
        try:
            r = await self._client.put(
                url,
                content=body.encode("utf-8"),
                headers={
                    "Content-Type": content_type,
                    "x-amz-acl": "private",
                },
                auth=(self.access_key, self.secret_key),
            )
        except httpx.HTTPError as exc:
            log.warning("artifact upload failed %s: %s", key, exc)
            return None
        if r.status_code not in {200, 201, 204}:
            log.warning("artifact upload HTTP %s for %s: %s", r.status_code, key, r.text[:200])
            return None
        return f"s3://{self.bucket}/{key}"


class NullArtifactStore:
    enabled = False

    async def aclose(self) -> None:
        return None

    async def put_text(self, **_: Any) -> str | None:
        return None


def build_artifact_store(settings: Any) -> ArtifactStore | NullArtifactStore:
    if not settings.minio_endpoint:
        return NullArtifactStore()
    endpoint = settings.minio_endpoint
    if not endpoint.startswith("http"):
        scheme = "https" if settings.minio_secure else "http"
        endpoint = f"{scheme}://{endpoint}"
    # Normalise host:port without path
    parsed = urlparse(endpoint)
    endpoint = f"{parsed.scheme}://{parsed.netloc}"
    return ArtifactStore(
        endpoint=endpoint,
        access_key=settings.minio_access_key or "emaw",
        secret_key=settings.minio_secret_key or "",
        bucket=settings.minio_bucket,
        secure=settings.minio_secure,
    )
