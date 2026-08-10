import json
import os
from pathlib import Path

APP_NAME = "取件码"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 环境变量可覆盖（测试/联调用）
DATA_DIR = Path(os.environ.get("QJK_DATA_DIR", str(PROJECT_ROOT / "data")))
CHAT_DB = Path(os.environ.get("QJK_CHAT_DB", str(Path.home() / "Library/Messages/chat.db")))
PORT = int(os.environ.get("QJK_PORT", "8787"))
HOST = os.environ.get("QJK_HOST", "0.0.0.0")

DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
DB_PATH = DATA_DIR / "data.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
STATE_PATH = DATA_DIR / "state.json"


def _atomic_write(path: Path, text: str) -> None:
    # 原子写（临时文件 + rename）+ 属主权限一步到位：避免读到半写内容，
    # 且即使进程崩溃，残留的 .tmp 也是 0600，不会泄露 bark_key/token
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    tmp.replace(path)


def save_json(path: Path, data) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


# 可选访问口令：设置 QJK_TOKEN 后所有 /api/* 请求必须带 X-QJK-Token 头；默认不启用
TOKEN = os.environ.get("QJK_TOKEN", "").strip()


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _atomic_write(path: Path, text: str) -> None:
    # 原子写（临时文件 + rename）+ 属主权限一步到位：避免读到半写内容，
    # 且即使进程崩溃，残留的 .tmp 也是 0600，不会泄露 bark_key/token
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    tmp.replace(path)


def save_json(path: Path, data) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


_settings_cache: dict | None = None


def get_settings() -> dict:
    """读缓存，仅在进程内首次调用时读盘（写少读多）。"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_json(SETTINGS_PATH, {"bark_key": ""})
    return _settings_cache


def save_settings(settings: dict) -> None:
    global _settings_cache
    _settings_cache = settings
    save_json(SETTINGS_PATH, settings)
