import importlib

import server.config as config


def test_no_env_token_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("QJK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("QJK_TOKEN", raising=False)
    importlib.reload(config)
    assert config.TOKEN == ""  # 默认不启用访问口令


def test_env_token_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("QJK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QJK_TOKEN", "my-token")
    importlib.reload(config)
    assert config.TOKEN == "my-token"


def test_env_token_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("QJK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QJK_TOKEN", "  spaced  ")
    importlib.reload(config)
    assert config.TOKEN == "spaced"


def test_data_dir_permissions(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("QJK_DATA_DIR", str(data_dir))
    importlib.reload(config)
    assert (data_dir.stat().st_mode & 0o777) == 0o700
