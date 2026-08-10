import hmac
import logging
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server import config
from server.database import Database
from server.notifier import notify_new_package, send_bark
from server.sms_monitor import SmsMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

db = Database(config.DB_PATH)


def _notify_on_new(pkg: dict) -> None:
    bark_key = config.get_settings().get("bark_key", "")
    if bark_key:
        notify_new_package(bark_key, pkg["station"], pkg["pickup_code"], pkg["express"])


# 只有显式设置 QJK_SKIP_MONITOR=1 才跳过监控；"0"/"false" 等其余值不跳过
if os.environ.get("QJK_SKIP_MONITOR") != "1":
    monitor = SmsMonitor(config.CHAT_DB, db, on_new=_notify_on_new)
    monitor.start()

if config.TOKEN:
    logging.getLogger("main").info("已启用访问口令（QJK_TOKEN）")

app = FastAPI(title="取件码")


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"  # API 含取件码等隐私数据，禁止任何缓存
    elif path == "/sw.js":
        resp.headers["Cache-Control"] = "no-cache"  # 安全修复后旧 SW 尽快失效
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    return resp


def require_token(x_qjk_token: str | None = Header(default=None)) -> None:
    """设置 QJK_TOKEN 后所有 /api/* 请求必须携带匹配的 X-QJK-Token 头；未设置则不鉴权。"""
    if config.TOKEN and (not x_qjk_token or not hmac.compare_digest(x_qjk_token, config.TOKEN)):
        raise HTTPException(401, "未授权：访问口令错误，请在设置页检查")


class PackageCreate(BaseModel):
    station: str = Field(max_length=64)
    pickup_code: str = Field(max_length=32)
    express: str | None = Field(default=None, max_length=16)


class SettingsBody(BaseModel):
    bark_key: str = Field(default="", max_length=64)


@app.get("/api/packages", dependencies=[Depends(require_token)])
def list_packages(status: str = "pending", page: int = 1, page_size: int = 10):
    if status not in ("pending", "collected"):
        raise HTTPException(400, "status 必须为 pending 或 collected")
    return db.list_packages(status, page, page_size)


@app.post("/api/packages", dependencies=[Depends(require_token)])
def add_manual(body: PackageCreate):
    station = body.station.strip()
    pickup_code = body.pickup_code.strip()
    if not station or not pickup_code:
        raise HTTPException(400, "驿站名和取件码不能为空")
    ok = db.add_manual(station, pickup_code, body.express.strip() if body.express else None)
    return {"ok": ok, "duplicated": not ok}


@app.delete("/api/packages/{pid}", dependencies=[Depends(require_token)])
def delete_package(pid: int):
    if not db.delete_package(pid):
        raise HTTPException(404, "包裹不存在")
    return {"ok": True}


@app.post("/api/packages/{pid}/collected", dependencies=[Depends(require_token)])
def mark_collected(pid: int):
    if not db.mark_collected(pid):
        raise HTTPException(404, "包裹不存在或已标记为已取")
    return {"ok": True}


@app.post("/api/packages/{pid}/pending", dependencies=[Depends(require_token)])
def mark_pending(pid: int):
    if not db.mark_pending(pid):
        raise HTTPException(404, "包裹不存在或未标记为已取")
    return {"ok": True}


@app.get("/api/settings", dependencies=[Depends(require_token)])
def get_settings():
    return {"bark_key": config.get_settings().get("bark_key", "")}


@app.put("/api/settings", dependencies=[Depends(require_token)])
def put_settings(body: SettingsBody):
    config.save_settings({"bark_key": body.bark_key.strip()})
    return {"ok": True}


@app.post("/api/notify/test", dependencies=[Depends(require_token)])
def notify_test():
    bark_key = config.get_settings().get("bark_key", "")
    if not bark_key:
        raise HTTPException(400, "请先填写 Bark key")
    if not send_bark(bark_key, "取件码·测试", "Bark 推送设置成功"):
        raise HTTPException(502, "推送失败，请检查 Bark key 是否正确")
    return {"ok": True}


web_dir = config.PROJECT_ROOT / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
