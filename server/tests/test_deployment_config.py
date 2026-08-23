import json
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERCEL_CONFIG = PROJECT_ROOT / "web" / "vercel.json"


def _load_config() -> dict:
    return json.loads(VERCEL_CONFIG.read_text("utf-8"))


def _headers_for(config: dict, source: str) -> dict[str, str]:
    rule = next(item for item in config["headers"] if item["source"] == source)
    return {item["key"]: item["value"] for item in rule["headers"]}


def test_api_rewrite_uses_tailscale_https_origin():
    config = _load_config()
    rewrite = next(item for item in config["rewrites"] if item["source"] == "/api/:path*")
    destination = rewrite["destination"]
    parsed = urlparse(destination.replace(":path*", "probe"))

    assert parsed.scheme == "https"
    assert parsed.hostname is not None
    assert parsed.hostname.endswith(".ts.net")
    assert parsed.path == "/api/probe"


def test_api_responses_are_not_cached():
    headers = _headers_for(_load_config(), "/api/:path*")
    assert headers["Cache-Control"] == "no-store"


def test_service_worker_is_revalidated():
    headers = _headers_for(_load_config(), "/sw.js")
    assert headers["Cache-Control"] == "no-cache"


def test_static_site_has_frame_and_content_security_headers():
    headers = _headers_for(_load_config(), "/(.*)")
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Content-Security-Policy"] == "default-src 'self'; frame-ancestors 'none'"
