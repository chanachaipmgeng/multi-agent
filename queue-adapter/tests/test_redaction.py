from app.redaction import redact, tail


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
