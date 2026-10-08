"""Unit tests for scripts/render-ingress.py (D4.3 prep)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render-ingress.py"


def _load():
    spec = importlib.util.spec_from_file_location("render_ingress", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render_ingress"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_rejects_placeholder_domain(tmp_path: Path) -> None:
    org = tmp_path / "org.yaml"
    org.write_text("org:\n  domain: '<to confirm>'\n", encoding="utf-8")
    mod = _load()
    with pytest.raises(SystemExit) as ei:
        mod.load_org(org)
    assert "DECISION-5" in str(ei.value)


def test_render_order_and_catch_all(tmp_path: Path) -> None:
    org = tmp_path / "org.yaml"
    org.write_text(
        "\n".join(
            [
                "org:",
                "  domain: example.test",
                "  cloudflare_account_owner: ops@example.test",
                "  webhook_hostname: webhook.<org-domain>",
                "  agents_hostname: agents.<org-domain>",
                "  grafana_hostname: grafana.<org-domain>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "cloudflared"
    mod = _load()
    assert mod.main(["--org", str(org), "--out-dir", str(out)]) == 0
    cfg_text = (out / "config.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(cfg_text)
    ingress = data["ingress"]
    assert len(ingress) == 4
    assert ingress[0]["hostname"] == "webhook.example.test"
    assert ingress[0]["path"] == "^/webhook/.*"
    assert ingress[0]["service"] == "http://localhost:8700"
    assert ingress[1]["hostname"] == "agents.example.test"
    assert ingress[1]["service"] == "http://localhost:9119"
    assert ingress[2]["hostname"] == "grafana.example.test"
    assert ingress[2]["service"] == "http://localhost:3000"
    assert ingress[3] == {"service": "http_status:404"}
    doc = (out / "access-and-waf.md").read_text(encoding="utf-8")
    assert 'http.host eq "webhook.example.test"' in doc
    assert "grafana.example.test" in doc
