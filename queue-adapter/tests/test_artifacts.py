"""MinIO / S3 artifact store (AWS SigV4)."""

from __future__ import annotations

import httpx
import pytest

from app.artifacts import ArtifactStore, NullArtifactStore, _sign_v4_headers, build_artifact_store
from app.settings import Settings


def test_sign_v4_headers_contain_authorization() -> None:
    headers = _sign_v4_headers(
        method="PUT",
        url="http://minio:9000/emaw-artifacts/proj/t-1/out.md",
        access_key="emaw",
        secret_key="secret",
        payload=b"hello",
        content_type="text/plain",
    )
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=emaw/")
    assert "Signature=" in headers["Authorization"]
    assert headers["Content-Type"] == "text/plain"
    assert "x-amz-content-sha256" in headers
    assert "x-amz-date" in headers
    assert "x-amz-acl" not in headers


@pytest.mark.asyncio
async def test_put_text_signs_and_uploads() -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization", "")
        seen["acl"] = request.headers.get("x-amz-acl")
        seen["body"] = request.content
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    store = ArtifactStore(
        endpoint="http://minio:9000",
        access_key="emaw",
        secret_key="secret",
        bucket="emaw-artifacts",
    )
    await store._client.aclose()
    store._client = httpx.AsyncClient(transport=transport, timeout=5.0)
    try:
        url = await store.put_text(
            project="frontend-app",
            task_id="t-1",
            name="run-output.md",
            body="# ok\n",
            content_type="text/markdown",
        )
    finally:
        await store.aclose()

    assert url == "s3://emaw-artifacts/frontend-app/t-1/run-output.md"
    assert seen["method"] == "PUT"
    assert seen["url"] == "http://minio:9000/emaw-artifacts/frontend-app/t-1/run-output.md"
    assert str(seen["authorization"]).startswith("AWS4-HMAC-SHA256")
    assert seen["acl"] is None
    assert seen["body"] == b"# ok\n"


def test_build_artifact_store_null_without_endpoint() -> None:
    settings = Settings(
        MODE="worker",
        ROLE="dev-frontend",
        REDIS_URL="redis://unused:6379/0",
        MINIO_ENDPOINT=None,
        METRICS_PORT=0,
    )
    store = build_artifact_store(settings)
    assert isinstance(store, NullArtifactStore)
