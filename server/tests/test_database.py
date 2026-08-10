import threading

import pytest

from server.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class TestAddPackage:
    def test_add_new(self, db):
        assert db.add_package(sms_id=1, station="菜鸟驿站·A店", pickup_code="4-1-2345",
                              express="中通", received_at="2026-08-10 10:00:00") is True

    def test_duplicate_sms_id_same_code_ignored(self, db):
        assert db.add_package(sms_id=1, station="菜鸟驿站·A店", pickup_code="4-1-2345",
                              express=None, received_at="2026-08-10 10:00:00") is True
        assert db.add_package(sms_id=1, station="菜鸟驿站·A店", pickup_code="4-1-2345",
                              express=None, received_at="2026-08-10 11:00:00") is False
        assert db.list_packages("pending", 1, 10)["total"] == 1

    def test_same_sms_multi_codes_inserted(self, db):
        # 真实场景：一条短信含多个取件码（"请凭A, B到店取件"）
        assert db.add_package(sms_id=5, station="菜鸟驿站·A店", pickup_code="4-1-2345",
                              express=None, received_at="2026-08-10 10:00:00") is True
        assert db.add_package(sms_id=5, station="菜鸟驿站·A店", pickup_code="4-1-9999",
                              express=None, received_at="2026-08-10 10:00:00") is True
        assert db.list_packages("pending", 1, 10)["total"] == 2

    def test_same_station_code_same_day_ignored(self, db):
        assert db.add_package(sms_id=1, station="妈妈驿站", pickup_code="8888",
                              express=None, received_at="2026-08-10 10:00:00") is True
        assert db.add_package(sms_id=2, station="妈妈驿站", pickup_code="8888",
                              express=None, received_at="2026-08-10 15:00:00") is False
        assert db.list_packages("pending", 1, 10)["total"] == 1

    def test_same_code_different_day_inserted(self, db):
        assert db.add_package(sms_id=1, station="妈妈驿站", pickup_code="8888",
                              express=None, received_at="2026-08-10 10:00:00") is True
        assert db.add_package(sms_id=2, station="妈妈驿站", pickup_code="8888",
                              express=None, received_at="2026-08-11 10:00:00") is True
        assert db.list_packages("pending", 1, 10)["total"] == 2

    def test_manual_no_sms_id(self, db):
        assert db.add_manual(station="菜鸟驿站·B店", pickup_code="1234") is True
        assert db.add_manual(station="菜鸟驿站·B店", pickup_code="1234") is False

    def test_manual_does_not_block_same_day_sms(self, db):
        # 手动补录后同日短信到达：短信应正常入库（不再被手动条目吞掉）
        assert db.add_manual(station="兔喜生活·鹭银海店", pickup_code="9-2-0401") is True
        assert db.add_package(sms_id=1, station="兔喜生活·鹭银海店", pickup_code="9-2-0401",
                              express=None, received_at="2026-08-10 11:30:00") is True
        assert db.list_packages("pending", 1, 10)["total"] == 2

    def test_sms_duplicate_different_sms_id_same_day_ignored(self, db):
        # 不同短信重复发同站同码（驿站重复提醒）应去重
        assert db.add_package(sms_id=1, station="站A", pickup_code="1234",
                              express=None, received_at="2026-08-10 10:00:00") is True
        assert db.add_package(sms_id=2, station="站A", pickup_code="1234",
                              express=None, received_at="2026-08-10 15:00:00") is False


class TestListPackages:
    def _seed(self, db):
        # 站 A 两条（10:00, 12:00），站 B 一条（13:00）→ B 组最新在前
        db.add_package(1, "站A", "A1", None, "2026-08-10 10:00:00")
        db.add_package(2, "站A", "A2", None, "2026-08-10 12:00:00")
        db.add_package(3, "站B", "B1", None, "2026-08-10 13:00:00")

    def test_group_order_latest_station_first(self, db):
        self._seed(db)
        items = db.list_packages("pending", 1, 10)["items"]
        stations = [i["station"] for i in items]
        assert stations == ["站B", "站A", "站A"]

    def test_within_group_time_desc(self, db):
        self._seed(db)
        items = db.list_packages("pending", 1, 10)["items"]
        assert items[1]["pickup_code"] == "A2"  # 12:00 在 10:00 前

    def test_group_tiebreak_by_station(self, db):
        # 两个驿站最新包裹时间相同时，组内行相邻不交错（按站名 tie-break）
        db.add_package(1, "站B", "B1", None, "2026-08-10 10:00:00")
        db.add_package(2, "站A", "A1", None, "2026-08-10 10:00:00")
        db.add_package(3, "站B", "B2", None, "2026-08-10 09:00:00")
        db.add_package(4, "站A", "A2", None, "2026-08-10 09:00:00")
        stations = [i["station"] for i in db.list_packages("pending", 1, 10)["items"]]
        assert stations == ["站A", "站A", "站B", "站B"]  # 站名升序稳定

    def test_pagination(self, db):
        for i in range(12):
            db.add_package(i, "站A", f"C{i}", None, f"2026-08-10 {10 + i // 60:02d}:{i:02d}:00")
        page1 = db.list_packages("pending", 1, 10)
        page2 = db.list_packages("pending", 2, 10)
        assert page1["total"] == 12 and len(page1["items"]) == 10
        assert len(page2["items"]) == 2
        assert page1["pages"] == 2

    def test_status_filter(self, db):
        self._seed(db)
        first = db.list_packages("pending", 1, 10)["items"][0]
        db.mark_collected(first["id"])
        pending = db.list_packages("pending", 1, 10)
        collected = db.list_packages("collected", 1, 10)
        assert pending["total"] == 2
        assert collected["total"] == 1
        assert collected["items"][0]["id"] == first["id"]


class TestStatus:
    def test_collect_and_undo(self, db):
        db.add_package(1, "站A", "A1", None, "2026-08-10 10:00:00")
        pid = db.list_packages("pending", 1, 10)["items"][0]["id"]
        assert db.mark_collected(pid) is True
        item = db.list_packages("collected", 1, 10)["items"][0]
        assert item["status"] == "collected" and item["collected_at"] is not None
        assert db.mark_pending(pid) is True
        assert db.list_packages("pending", 1, 10)["total"] == 1

    def test_mark_missing_id(self, db):
        assert db.mark_collected(999) is False


class TestDelete:
    def test_delete(self, db):
        db.add_package(1, "站A", "A1", None, "2026-08-10 10:00:00")
        pid = db.list_packages("pending", 1, 10)["items"][0]["id"]
        assert db.delete_package(pid) is True
        assert db.list_packages("pending", 1, 10)["total"] == 0

    def test_delete_missing(self, db):
        assert db.delete_package(999) is False


class TestConcurrency:
    def test_concurrent_reads_and_writes(self, db):
        # 模拟真实运行：monitor 线程写入 + 网页请求线程读取
        errors = []

        def writer():
            try:
                for i in range(50):
                    db.add_package(i, f"站{i % 3}", f"code-{i}", None,
                                   f"2026-08-10 {(i % 24):02d}:{i % 60:02d}:00")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def reader():
            try:
                for _ in range(30):
                    db.list_packages("pending", 1, 10)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert db.list_packages("pending", 1, 10)["total"] == 50
