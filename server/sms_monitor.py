import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from server import config
from server.parser import KEYWORDS, parse_sms_multi

log = logging.getLogger("sms_monitor")

# chat.db 的 date 是 Mac 绝对时间（2001-01-01 起秒数）
MAC_EPOCH_OFFSET = 978307200
RECENT_WINDOW_DAYS = 30
POLL_INTERVAL = 30  # 秒，watchdog 失效时的兜底轮询
FAIL_BACKOFF_INTERVAL = 300  # 秒，连续失败（如 TCC 未授权）时轮询降频，避免日志刷屏


def _to_seconds(chat_date: int) -> float:
    # 新版 macOS date 为纳秒精度（>1e12），旧版为秒；混合库中逐行判断
    return chat_date / 1e9 if chat_date > 1e12 else chat_date


def _received_at(chat_date: int) -> str:
    return datetime.fromtimestamp(_to_seconds(chat_date) + MAC_EPOCH_OFFSET).strftime("%Y-%m-%d %H:%M:%S")


def _decode_text(blob: bytes | None) -> str:
    # 新版 macOS 短信内容在 attributedBody（NSKeyedArchiver），文本为 UTF-8 明文
    if not blob:
        return ""
    return blob.decode("utf-8", errors="ignore")


class SmsMonitor:
    def __init__(self, chat_db: Path, db, on_new: Callable[[dict], None] | None = None,
                 state_path: Path | None = None):
        self.chat_db = Path(chat_db)
        self.db = db
        self.on_new = on_new
        self.state_path = Path(state_path) if state_path else config.STATE_PATH
        self.last_date = 0.0  # 秒级 Mac 绝对时间（混合刻度归一化后），持久化
        self.last_id = 0
        self._lock = threading.Lock()
        self._fail_streak = 0
        state = config.load_json(self.state_path, {})
        try:
            if state.get("last_date") and state.get("last_id") is not None:
                self.last_date = float(state["last_date"])
                self.last_id = int(state["last_id"])
        except (ValueError, TypeError):
            log.warning("state.json 损坏，已重置监控游标: %s", self.state_path)
            self.last_date = 0.0
            self.last_id = 0

    def sync_once(self) -> int:
        """处理新短信，返回新入库的包裹数。推送在锁外执行，不阻塞同步。"""
        if not self.chat_db.exists():
            log.warning("短信数据库不存在: %s", self.chat_db)
            self._fail_streak += 1
            return 0
        with self._lock:
            new_count, new_items = self._sync()
        for item in new_items:
            if self.on_new:
                try:
                    self.on_new(item)
                except Exception:
                    log.exception("新包裹回调失败")
        return new_count

    def _sync(self) -> tuple[int, list[dict]]:
        try:
            conn = sqlite3.connect(f"file:{self.chat_db}?mode=ro", uri=True)
        except sqlite3.Error as e:
            log.error("无法打开短信数据库 %s（%s）。请在 系统设置 > 隐私与安全性 > 信息与照片 中授权。", self.chat_db, e)
            self._fail_streak += 1
            return 0, []
        try:
            window_sec = time.time() - MAC_EPOCH_OFFSET - RECENT_WINDOW_DAYS * 86400
            # SQL 下界用秒级（纳秒行必然 >= 秒级下界而进入扫描），刻度归一化在 Python 层逐行做，
            # 以兼容混合刻度库（macOS 升级/iCloud 恢复后秒/纳秒并存）
            rows = conn.execute(
                "SELECT ROWID, date, attributedBody FROM message "
                "WHERE attributedBody IS NOT NULL AND date >= ? ORDER BY date, ROWID",
                (int(window_sec),),
            ).fetchall()
            new_count = 0
            new_items: list[dict] = []
            last_ts = self.last_date
            last_id = self.last_id
            # 本次 sync 开始时有游标才推送：全新启动（无游标）首次只回填，避免历史短信推送轰炸
            notify = last_ts > 0
            for msg_id, chat_date, blob in rows:
                ts = _to_seconds(chat_date)
                if ts < window_sec:
                    continue  # 窗口外（混合刻度中的纳秒旧行）
                # 全窗口重扫 + DB 幂等去重：游标前的回填行（iCloud 恢复等）也能入库，
                # 只是不算"新到"不推送
                is_after_cursor = ts > last_ts or (ts == last_ts and msg_id > last_id)
                text = _decode_text(blob)
                if KEYWORDS.search(text):
                    parsed_list = parse_sms_multi(text)
                    if not parsed_list:
                        log.info("短信含快递关键词但未解析出取件码: %s", text[:20])
                    for parsed in parsed_list:
                        inserted = self.db.add_package(
                            sms_id=msg_id,
                            station=parsed.station,
                            pickup_code=parsed.pickup_code,
                            express=parsed.express,
                            received_at=_received_at(chat_date),
                            sms_text=text,
                        )
                        if inserted:
                            new_count += 1
                            log.info("新取件码: %s @ %s (%s)", parsed.pickup_code, parsed.station, parsed.express or "")
                            if notify and is_after_cursor:
                                new_items.append({
                                    "station": parsed.station,
                                    "pickup_code": parsed.pickup_code,
                                    "express": parsed.express,
                                })
                last_ts = ts
                last_id = msg_id
            self.last_date = last_ts
            self.last_id = last_id
            config.save_json(self.state_path, {"last_date": last_ts, "last_id": last_id})
            self._fail_streak = 0
            return new_count, new_items
        except sqlite3.Error as e:
            log.error("读取短信数据库失败: %s", e)
            self._fail_streak += 1
            return 0, []
        finally:
            conn.close()

    def start(self) -> None:
        """启动监控：立即同步一次，然后 watchdog + 兜底轮询。"""
        self.sync_once()
        handler = _ChatDbHandler(self)
        observer = Observer()
        observer.daemon = True
        observer.schedule(handler, str(self.chat_db.parent), recursive=False)
        observer.start()

        def poll_loop():
            while True:
                interval = POLL_INTERVAL if self._fail_streak < 3 else FAIL_BACKOFF_INTERVAL
                time.sleep(interval)
                try:
                    self.sync_once()
                except Exception:
                    log.exception("轮询同步失败")

        t = threading.Thread(target=poll_loop, daemon=True)
        t.start()


class _ChatDbHandler(FileSystemEventHandler):
    def __init__(self, monitor: SmsMonitor):
        self.monitor = monitor
        self._last_trigger = 0

    def on_any_event(self, event):
        if self._last_trigger and time.time() - self._last_trigger < 0.5:
            return  # 去抖：chat.db 常伴随 -wal 文件多次事件
        self._last_trigger = time.time()
        try:
            self.monitor.sync_once()
        except Exception:
            log.exception("文件变化同步失败")
