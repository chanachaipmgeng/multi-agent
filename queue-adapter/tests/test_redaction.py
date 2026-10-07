from app.redaction import redact, redact_attrs, tail
from app.notify import dispatch_failed_text, dead_letter_text


def test_redacts_known_token_shapes() -> None:
    text = (
        "token glpat-abcdefghijklmnopqrstuvwxyz12 and sk-abcdefghijklmnopqrstuvwxyz "
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig "
        "AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ "
        "bot 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi "
        "DB_PASSWORD=hunter2hunter2 API_KEY: 'abcdef123456' "
        "https://user:pa55word@gitlab.example.com/repo.git"
    )
    out = redact(text)
    for secret in (
        "abcdefghijklmnopqrstuvwxyz12",
        "eyJhbGciOiJIUzI1NiJ9",
        "QQQQQQQQ",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        "hunter2hunter2",
        "abcdef123456",
        "pa55word",
    ):
        assert secret not in out, secret
    assert "glpat-[REDACTED]" in out
    assert "DB_PASSWORD=[REDACTED]" in out
    assert "https://[REDACTED]@gitlab.example.com" in out


def test_redaction_keeps_normal_log_lines() -> None:
    line = "ERROR: Could not find a version that satisfies the requirement foo==9.9.9"
    assert redact(line) == line


def test_private_key_block_redacted() -> None:
    text = "before\n-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\nafter"
    out = redact(text)
    assert "MIIE" not in out and "[REDACTED-PRIVATE-KEY]" in out


def test_tail_keeps_end_of_log() -> None:
    text = "".join(f"line {i}\n" for i in range(1000))
    out = tail(text, 200)
    assert out.startswith("…[truncated")
    assert out.rstrip().endswith("line 999")
    assert tail("short", 200) == "short"


def test_redact_attrs_nested() -> None:
    attrs = {
        "detail": "fail Bearer sk-abcdefghijklmnopqrstuvwxyz",
        "nested": {"token": "glpat-abcdefghijklmnopqrstuvwxyz12"},
        "n": 1,
    }
    out = redact_attrs(attrs)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in out["detail"]
    assert "abcdefghijklmnopqrstuvwxyz12" not in out["nested"]["token"]
    assert out["n"] == 1


def test_notify_helpers_redact_detail() -> None:
    task = {"task_id": "t1", "trace_id": "tr"}
    secret = "sk-abcdefghijklmnopqrstuvwxyz"
    assert secret not in dispatch_failed_text(task, f"err {secret}", 1, 3)
    assert secret not in dead_letter_text(task, f"dead {secret}")


async def test_telegram_send_redacts() -> None:
    """Notifier.send redacts before POST body."""
    import json

    import httpx
    from app.notify import TelegramNotifier

    captured: list[dict] = []

    class CaptureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content.decode()))
            return httpx.Response(200, json={"ok": True})

    n = TelegramNotifier("token", "123", transport=CaptureTransport())
    await n.send("leak sk-abcdefghijklmnopqrstuvwxyz here")
    await n.aclose()
    assert captured
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in captured[0]["text"]
    assert "sk-[REDACTED]" in captured[0]["text"]
