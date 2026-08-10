import urllib.request

import pytest

from server import notifier


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_empty_key_skips_request(monkeypatch):
    called = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: called.append(a) or _Resp())
    assert notifier.send_bark("", "t", "b") is False
    assert called == []


def test_success(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(200))
    assert notifier.send_bark("abc", "标题", "正文") is True


def test_http_error_fails(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(500))
    assert notifier.send_bark("abc", "t", "b") is False


def test_network_error_fails(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert notifier.send_bark("abc", "t", "b") is False


def test_url_encodes_key_and_text(monkeypatch):
    seen = {}

    def fake_urlopen(url, *a, **k):
        seen["url"] = url
        return _Resp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    notifier.send_bark("a/b", "标题", "正文")
    assert "a%2Fb" in seen["url"]  # key 也转义，防 URL 路径注入
    assert "%E6%A0%87%E9%A2%98" in seen["url"]  # 标题 UTF-8 编码


def test_notify_new_package_assembles_body(monkeypatch):
    seen = {}

    def fake_urlopen(url, *a, **k):
        seen["url"] = url
        return _Resp(200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    notifier.notify_new_package("key", "菜鸟驿站·A店", "4-1-2345", "中通")
    decoded = urllib.request.unquote(seen["url"])
    assert "4-1-2345" in decoded and "菜鸟驿站·A店" in decoded and "中通" in decoded
