import os
import sqlite3
import threading
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  station     TEXT NOT NULL,
  pickup_code TEXT NOT NULL,
  express     TEXT,
  sms_text    TEXT,
  sms_id      INTEGER,
  received_at TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',
  collected_at TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE(sms_id, pickup_code)
);
CREATE INDEX IF NOT EXISTS idx_status_received ON packages(status, received_at DESC);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        try:
            os.chmod(path, 0o600)  # 快递取件码属个人隐私数据，仅当前用户可读写
        except OSError:
            pass

    def add_package(self, sms_id, station, pickup_code, express, received_at,
                    sms_text=None) -> bool:
        """返回 True 表示新插入，False 表示重复被忽略。

        短信（sms_id 非空）与手动条目（sms_id 为 NULL）去重规则分离：
        - 短信：同 sms_id+code 判重，另防不同短信的同站同码同日重复（驿站重复发短信）
        - 手动：同站同码同日判重，且不阻挡同日短信入库（手动补录后短信到达仍入库并推送）
        """
        with self._lock:
            if sms_id is not None:
                if self._conn.execute(
                    "SELECT 1 FROM packages WHERE sms_id = ? AND pickup_code = ?",
                    (sms_id, pickup_code),
                ).fetchone():
                    return False
                if self._conn.execute(
                    "SELECT 1 FROM packages WHERE sms_id IS NOT NULL AND station = ? "
                    "AND pickup_code = ? AND substr(received_at, 1, 10) = substr(?, 1, 10)",
                    (station, pickup_code, received_at),
                ).fetchone():
                    return False
            elif self._conn.execute(
                "SELECT 1 FROM packages WHERE station = ? AND pickup_code = ? "
                "AND substr(received_at, 1, 10) = substr(?, 1, 10)",
                (station, pickup_code, received_at),
            ).fetchone():
                return False
            self._conn.execute(
                "INSERT INTO packages (station, pickup_code, express, sms_text, sms_id, "
                "received_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (station, pickup_code, express, sms_text, sms_id, received_at, _now()),
            )
            self._conn.commit()
            return True

    def add_manual(self, station, pickup_code, express=None) -> bool:
        return self.add_package(None, station, pickup_code, express, _now())

    def list_packages(self, status, page, page_size) -> dict:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM packages WHERE status = ?", (status,)
            ).fetchone()[0]
            rows = self._conn.execute(
                "SELECT p.id, p.station, p.pickup_code, p.express, p.sms_id, p.received_at, "
                "p.status, p.collected_at, p.created_at FROM packages p "
                "JOIN (SELECT station, MAX(received_at) AS latest FROM packages "
                "      WHERE status = ? GROUP BY station) g ON p.station = g.station "
                "WHERE p.status = ? "
                "ORDER BY g.latest DESC, g.station ASC, p.received_at DESC, p.id DESC "
                "LIMIT ? OFFSET ?",
                (status, status, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }

    def mark_collected(self, pid) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE packages SET status = 'collected', collected_at = ? WHERE id = ? "
                "AND status = 'pending'",
                (_now(), pid),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def mark_pending(self, pid) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE packages SET status = 'pending', collected_at = NULL WHERE id = ? "
                "AND status = 'collected'",
                (pid,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_package(self, pid) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM packages WHERE id = ?", (pid,))
            self._conn.commit()
            return cur.rowcount > 0
