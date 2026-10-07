"""Optional MinIO / S3 artifact uploads (design D3.7)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx

log = logging.getLogger("emaw.adapter.artifacts")


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign_v4_headers(
    *,
    method: str,
    url: str,
    access_key: str,
    secret_key: str,
    payload: bytes,
    content_type: str,
    region: str = "us-east-1",
) -> dict[str, str]:
    """AWS Signature Version 4 headers for a single PUT/GET (path-style)."""
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = quote(parsed.path or "/", safe="/-_.~")
    amz_date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    date_stamp = amz_date[:8]
    payload_hash = _sha256_hex(payload)
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            "",  # no query string
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )
    signing_key = _hmac_sha256(
        _hmac_sha256(
            _hmac_sha256(
                _hmac_sha256(f"AWS4{secret_key}".encode("utf-8"), date_stamp),
                region,
            ),
            "s3",
        ),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }


class ArtifactStore:
    """Minimal S3-compatible PUT via HTTP + AWS SigV4 (no boto3 dependency)."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        region: str = "us-east-1",
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self.region = region
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
        payload = body.encode("utf-8")
        headers = _sign_v4_headers(
            method="PUT",
            url=url,
            access_key=self.access_key,
            secret_key=self.secret_key,
            payload=payload,
            content_type=content_type,
            region=self.region,
        )
        try:
            r = await self._client.put(url, content=payload, headers=headers)
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
