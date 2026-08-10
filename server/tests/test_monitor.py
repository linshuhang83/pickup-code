import sqlite3
import time

import pytest

from server.database import Database
from server.sms_monitor import SmsMonitor

# chat.db 的 date 是 Mac 绝对时间（2001-01-01 起秒数）
MAC_EPOCH_OFFSET = 978307200


def _chat_date(unix_ts: float) -> int:
    return int(unix_ts - MAC_EPOCH_OFFSET)


@pytest.fixture
def chat_db(tmp_path):
    path = tmp_path / "chat.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE message (ROWID INTEGER PRIMARY KEY, date INTEGER, text TEXT, attributedBody BLOB)")
    conn.commit()
    return path


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "data.db")


@pytest.fixture
def monitor(chat_db, db, tmp_path):
    return SmsMonitor(chat_db, db, state_path=tmp_path / "state.json")


def _add_sms(chat_db, text, unix_ts, nanos=False):
    """真实 chat.db 的 text 列为 NULL，内容在 attributedBody。"""
    conn = sqlite3.connect(chat_db)
    date = int((unix_ts - MAC_EPOCH_OFFSET) * 1e9) if nanos else _chat_date(unix_ts)
    conn.execute("INSERT INTO message (date, text, attributedBody) VALUES (?, NULL, ?)", (date, text.encode("utf-8")))
    conn.commit()
    conn.close()


class TestSyncOnce:
    def test_parses_new_pickup_sms(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】您的包裹已到朝阳花园店，取件码 4-1-2345，请及时取件。", now)
        assert monitor.sync_once() == 1
        items = db.list_packages("pending", 1, 10)["items"]
        assert len(items) == 1
        assert items[0]["pickup_code"] == "4-1-2345"
        assert "朝阳花园店" in items[0]["station"]

    def test_idempotent_resync(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【妈妈驿站】您的快递已到店，取件码：6-2-8888。", now)
        monitor.sync_once()
        assert monitor.sync_once() == 0
        assert db.list_packages("pending", 1, 10)["total"] == 1

    def test_incremental_new_sms(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【妈妈驿站】您的快递已到店，取件码：6-2-8888。", now - 60)
        monitor.sync_once()
        _add_sms(chat_db, "【兔喜快递超市】包裹已到，取件码 5-1-2222。", now)
        assert monitor.sync_once() == 1
        assert db.list_packages("pending", 1, 10)["total"] == 2

    def test_non_pickup_sms_ignored(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【美团】您的验证码为123456，5分钟内有效。", now)
        assert monitor.sync_once() == 0

    def test_recent_window_only(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】您的包裹已到店，取件码 1-1-1111。", now - 90 * 86400)
        assert monitor.sync_once() == 0

    def test_same_second_duplicate_handled(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】包裹已到A店，取件码 2-2-2222。", now)
        monitor.sync_once()
        _add_sms(chat_db, "【菜鸟驿站】包裹已到B店，取件码 3-3-3333。", now)  # 同一秒
        assert monitor.sync_once() == 1
        assert db.list_packages("pending", 1, 10)["total"] == 2

    def test_missing_chat_db_does_not_crash(self, tmp_path, db):
        monitor = SmsMonitor(tmp_path / "not_exist.db", db, state_path=tmp_path / "state.json")
        assert monitor.sync_once() == 0

    def test_nanosecond_dates_parsed(self, chat_db, db, monitor):
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】包裹已到店，取件码 7-7-7777。", now, nanos=True)
        assert monitor.sync_once() == 1
        items = db.list_packages("pending", 1, 10)["items"]
        assert items[0]["pickup_code"] == "7-7-7777"

    def test_mixed_scale_dates_parsed(self, chat_db, db, monitor):
        # 混合刻度库：秒级行与纳秒级行并存都应解析（旧版/新版 macOS 迁移场景）
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】秒级短信取件码 1-2-3333。", now, nanos=False)
        _add_sms(chat_db, "【兔喜生活】纳秒短信取件码 8-8-8888。", now, nanos=True)
        assert monitor.sync_once() == 2
        codes = {i["pickup_code"] for i in db.list_packages("pending", 1, 10)["items"]}
        assert codes == {"1-2-3333", "8-8-8888"}

    def test_backfill_old_sms_after_cursor_inserted(self, chat_db, db, monitor):
        # 游标已推进后回填的旧日期短信（iCloud 恢复）仍应入库
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】新短信取件码 4-4-4444。", now)
        monitor.sync_once()
        _add_sms(chat_db, "【兔喜生活】回填旧短信取件码 5-5-5555。", now - 2 * 86400)
        assert monitor.sync_once() == 1
        assert db.list_packages("pending", 1, 10)["total"] == 2

    def test_first_boot_no_notify(self, chat_db, db, monitor):
        # 无持久化游标（全新启动/丢状态）：首次同步只回填不推送，避免历史短信轰炸
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】历史短信取件码 1-1-1000。", now - 5 * 86400)
        _add_sms(chat_db, "【妈妈驿站】历史短信取件码 2-2-2000。", now - 3 * 86400)
        calls = []
        monitor.on_new = calls.append
        assert monitor.sync_once() == 2
        assert calls == []

    def test_after_cursor_notify(self, chat_db, db, monitor):
        # 游标建立后（重启恢复或运行中）新短信应触发推送
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】旧短信取件码 3-3-3000。", now - 60)
        monitor.sync_once()
        calls = []
        monitor.on_new = calls.append
        _add_sms(chat_db, "【兔喜生活】新短信取件码 6-6-6000。", now)
        assert monitor.sync_once() == 1
        assert calls and calls[0]["pickup_code"] == "6-6-6000"

    def test_cursor_persisted_across_restart(self, chat_db, db, tmp_path):
        # 重启后从 state 恢复游标：不重扫旧短信（新实例 sync 返回 0），之后新短信正常推送
        now = time.time()
        _add_sms(chat_db, "【菜鸟驿站】重启前短信取件码 9-9-9999。", now - 60)
        SmsMonitor(chat_db, db, state_path=tmp_path / "state.json").sync_once()
        new = SmsMonitor(chat_db, db, state_path=tmp_path / "state.json")
        assert new.sync_once() == 0
        _add_sms(chat_db, "【兔喜生活】重启后短信取件码 1-1-1111。", now)
        assert new.sync_once() == 1
        assert db.list_packages("pending", 1, 10)["total"] == 2
