import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_TEST_DIR = tempfile.mkdtemp(prefix="qjk-api-test-")
os.environ["QJK_DATA_DIR"] = _TEST_DIR
os.environ["QJK_SKIP_MONITOR"] = "1"

from server import main  # noqa: E402
from server.database import Database  # noqa: E402


_TEST_TOKEN = "test-token-123"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "db", Database(tmp_path / "api.db"))
    monkeypatch.setattr("server.config.TOKEN", _TEST_TOKEN)
    return TestClient(main.app, headers={"X-QJK-Token": _TEST_TOKEN})


class TestPackages:
    def test_add_and_list(self, client):
        r = client.post("/api/packages", json={"station": "菜鸟驿站·测试店", "pickup_code": "4-1-2345"})
        assert r.status_code == 200 and r.json()["ok"] is True
        data = client.get("/api/packages").json()
        assert data["total"] == 1
        assert data["items"][0]["pickup_code"] == "4-1-2345"

    def test_add_duplicate(self, client):
        body = {"station": "站A", "pickup_code": "1234"}
        client.post("/api/packages", json=body)
        r = client.post("/api/packages", json=body)
        assert r.json()["duplicated"] is True

    def test_add_empty_rejected(self, client):
        assert client.post("/api/packages", json={"station": "", "pickup_code": "1234"}).status_code == 400

    def test_invalid_status(self, client):
        assert client.get("/api/packages?status=all").status_code == 400


class TestStatusFlow:
    def test_collect_and_undo(self, client):
        client.post("/api/packages", json={"station": "站A", "pickup_code": "1234"})
        pid = client.get("/api/packages").json()["items"][0]["id"]
        assert client.post(f"/api/packages/{pid}/collected").json()["ok"] is True
        assert client.get("/api/packages?status=pending").json()["total"] == 0
        assert client.get("/api/packages?status=collected").json()["total"] == 1
        assert client.post(f"/api/packages/{pid}/pending").json()["ok"] is True
        assert client.get("/api/packages?status=pending").json()["total"] == 1

    def test_double_collect_404(self, client):
        client.post("/api/packages", json={"station": "站A", "pickup_code": "1234"})
        pid = client.get("/api/packages").json()["items"][0]["id"]
        client.post(f"/api/packages/{pid}/collected")
        assert client.post(f"/api/packages/{pid}/collected").status_code == 404

    def test_missing_id_404(self, client):
        assert client.post("/api/packages/999/collected").status_code == 404


class TestDelete:
    def test_delete_package(self, client):
        client.post("/api/packages", json={"station": "站A", "pickup_code": "1234"})
        pid = client.get("/api/packages").json()["items"][0]["id"]
        assert client.delete(f"/api/packages/{pid}").json()["ok"] is True
        assert client.get("/api/packages").json()["total"] == 0

    def test_delete_missing_404(self, client):
        assert client.delete("/api/packages/999").status_code == 404


class TestTokenAuth:
    def test_missing_token_rejected(self, client):
        r = client.get("/api/packages", headers={"X-QJK-Token": ""})
        assert r.status_code == 401

    def test_wrong_token_rejected(self, client):
        r = client.get("/api/packages", headers={"X-QJK-Token": "wrong"})
        assert r.status_code == 401

    def test_correct_token_accepted(self, client):
        r = client.get("/api/packages", headers={"X-QJK-Token": _TEST_TOKEN})
        assert r.status_code == 200

    def test_write_endpoints_also_require_token(self, client):
        empty = {"X-QJK-Token": ""}
        assert client.post("/api/packages", headers=empty, json={"station": "站A", "pickup_code": "1234"}).status_code == 401
        assert client.put("/api/settings", headers=empty, json={"bark_key": "x"}).status_code == 401

    def test_no_token_configured_allows_anonymous(self, client, monkeypatch):
        # 默认（未设置 QJK_TOKEN）不鉴权，任何请求放行
        monkeypatch.setattr("server.config.TOKEN", "")
        r = client.get("/api/packages", headers={"X-QJK-Token": ""})
        assert r.status_code == 200


class TestSecurityHeaders:
    def test_api_no_store(self, client):
        assert client.get("/api/packages").headers["cache-control"] == "no-store"

    def test_sw_no_cache(self, client):
        assert client.get("/sw.js").headers["cache-control"] == "no-cache"

    def test_frame_protection(self, client):
        for path in ("/api/packages", "/", "/app.js"):
            r = client.get(path)
            assert r.headers["x-frame-options"] == "DENY"
            assert "frame-ancestors 'none'" in r.headers["content-security-policy"]

    def test_list_excludes_sms_text(self, client):
        client.post("/api/packages", json={"station": "站A", "pickup_code": "1234"})
        items = client.get("/api/packages").json()["items"]
        assert "sms_text" not in items[0]


class TestInputLimits:
    def test_overlong_station_rejected(self, client):
        r = client.post("/api/packages", json={"station": "站" * 65, "pickup_code": "1234"})
        assert r.status_code == 422

    def test_overlong_code_rejected(self, client):
        r = client.post("/api/packages", json={"station": "站A", "pickup_code": "X" * 33})
        assert r.status_code == 422

    def test_overlong_bark_key_rejected(self, client):
        r = client.put("/api/settings", json={"bark_key": "k" * 65})
        assert r.status_code == 422


class TestSettings:
    def test_get_put(self, client, tmp_path):
        assert client.get("/api/settings").json() == {"bark_key": ""}
        client.put("/api/settings", json={"bark_key": "abc123"})
        assert client.get("/api/settings").json() == {"bark_key": "abc123"}

    def test_notify_test_without_key(self, client):
        client.put("/api/settings", json={"bark_key": ""})
        assert client.post("/api/notify/test").status_code == 400
