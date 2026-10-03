"""月份批量结账 / 结账状态列表 / 同步月份数据 测试（跑在独立账套 t10）"""
import io

import pytest
from openpyxl import Workbook

from conftest import api, delete, get, post, put, upload

B = "book_id=t10"


def p(path):
    return path + ("&" if "?" in path else "?") + B


HEADERS = ["凭证号", "凭证日期", "摘要", "科目编码", "借方金额", "贷方金额"]


def row(no, date, summary, code, debit, credit):
    return [no, date, summary, code, debit, credit]


def xlsx(rows, headers=HEADERS):
    wb = Workbook()
    ws = wb.active
    ws.title = "凭证导入"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def periods_map():
    return {x["period"]: x for x in get(p("/api/carryover/periods"))[1]}


@pytest.fixture(scope="module", autouse=True)
def book(server):
    delete("/api/booksets/t10")
    st, r = post("/api/booksets", {"id": "t10", "name": "批量结账测试账套", "opening_year": "2034"})
    assert st == 200
    # 导入三个月凭证（含其它系统常见的负数利息收入）
    data = xlsx([
        row("记-001", "2034-01-05", "提现备用金", "1001", 1000, 0),
        row("记-001", "2034-01-05", "提现备用金", "1002", 0, 1000),
        row("记-002", "2034-02-05", "3月份银行收款(利息)", "1002", 1.01, 0),
        row("记-002", "2034-02-05", "3月份银行收款(利息)", "560301", -1.01, 0),
        row("记-003", "2034-03-05", "办公费", "560204", 200, 0),
        row("记-003", "2034-03-05", "办公费", "1002", 0, 200),
    ])
    st, r = upload(p("/api/data/import/vouchers"), "months.xlsx", data)
    assert st == 200, r
    assert r["created"] == 3 and r["red_rows"] == 1
    yield
    delete("/api/booksets/t10")


class TestMonthStatus:
    def test_月份列表含每月数据(self):
        rows = periods_map()
        for m in ("2034-01", "2034-02", "2034-03"):
            assert m in rows
            assert rows[m]["status"] == "open"
            assert rows[m]["voucher_count"] == 1
            assert rows[m]["import_count"] == 1
            assert rows[m]["draft_count"] == 0

    def test_月份借贷合计含红字带符号合计(self):
        rows = periods_map()
        assert rows["2034-01"]["total_debit"] == 1000
        assert rows["2034-01"]["total_credit"] == 1000
        # 红字（负数）原样参与合计：1.01 + -1.01 = 0
        assert rows["2034-02"]["total_debit"] == 0
        assert rows["2034-02"]["total_credit"] == 0

    def test_列表按期间倒序(self):
        periods = [x["period"] for x in get(p("/api/carryover/periods"))[1]]
        assert periods == sorted(periods, reverse=True)


class TestSyncMonths:
    def test_同步指定月份创建会计期间(self):
        st, r = post(p("/api/carryover/periods/sync"), {"periods": ["2034-09"]})
        assert st == 200, r
        assert "2034-09" in r["created"]
        rows = periods_map()
        assert "2034-09" in rows and rows["2034-09"]["status"] == "open"

    def test_同步全部月份(self):
        st, r = post(p("/api/carryover/periods/sync"), {})
        assert st == 200
        assert set(r["synced"]) >= {"2034-01", "2034-02", "2034-03"}

    def test_重复同步幂等(self):
        st, r = post(p("/api/carryover/periods/sync"), {"periods": ["2034-09"]})
        assert st == 200 and r["created"] == []

    def test_同步非法期间报错(self):
        st, r = post(p("/api/carryover/periods/sync"), {"periods": ["2034-13"]})
        assert st == 400


class TestBatchClose:
    def test_批量结账跳过检查(self):
        st, r = post(p("/api/carryover/close-batch"), {
            "periods": ["2034-01", "2034-02", "2034-03"],
            "skip_checks": True, "note": "历史数据已在其它系统结账"})
        assert st == 200, r
        assert r["closed"] == 3 and r["failed"] == 0
        rows = periods_map()
        for m in ("2034-01", "2034-02", "2034-03"):
            assert rows[m]["status"] == "closed"
            assert rows[m]["closed_at"]
            assert "其它系统" in rows[m]["note"]

    def test_结账后新增凭证被拒(self):
        st, r = post(p("/api/vouchers"), {
            "date": "2034-01-20",
            "entries": [{"account_id": _acc("560204"), "summary": "结账后", "debit": 10},
                        {"account_id": _acc("1002"), "summary": "结账后", "credit": 10}]})
        assert st == 400 and "已结账" in r["detail"]

    def test_批量反结账(self):
        st, r = post(p("/api/carryover/open-batch"), {"periods": ["2034-01", "2034-02", "2034-03"]})
        assert st == 200 and r["opened"] == 3 and r["failed"] == 0
        rows = periods_map()
        for m in ("2034-01", "2034-02", "2034-03"):
            assert rows[m]["status"] == "open" and not rows[m]["closed_at"]

    def test_草稿月份跳过检查可结账(self):
        st, r = post(p("/api/vouchers"), {
            "date": "2034-04-10", "status": "draft",
            "entries": [{"account_id": _acc("560204"), "summary": "草稿", "debit": 10},
                        {"account_id": _acc("1002"), "summary": "草稿", "credit": 10}]})
        assert st == 200 and r["status"] == "draft"
        st, r = post(p("/api/carryover/close-batch"), {
            "periods": ["2034-04"], "skip_checks": True})
        assert st == 200 and r["closed"] == 1 and r["failed"] == 0
        assert periods_map()["2034-04"]["status"] == "closed"

    def test_未跳过检查时草稿月份失败其他成功(self):
        assert post(p("/api/carryover/open-batch"), {"periods": ["2034-04"]})[0] == 200
        st, r = post(p("/api/carryover/close-batch"), {"periods": ["2034-04", "2034-01"]})
        assert st == 200
        assert r["closed"] == 1 and r["failed"] == 1
        by = {x["period"]: x for x in r["results"]}
        assert by["2034-01"]["ok"] is True
        assert by["2034-04"]["ok"] is False and "草稿" in by["2034-04"]["error"]
        rows = periods_map()
        assert rows["2034-01"]["status"] == "closed"
        assert rows["2034-04"]["status"] == "open"

    def test_批量结账非法期间逐月报错(self):
        st, r = post(p("/api/carryover/close-batch"), {"periods": ["bad", "2034-02"], "skip_checks": True})
        assert st == 200
        assert r["closed"] == 1 and r["failed"] == 1
        by = {x["period"]: x for x in r["results"]}
        assert by["bad"]["ok"] is False
        assert periods_map()["2034-02"]["status"] == "closed"

    def test_未选择期间报错(self):
        st, r = post(p("/api/carryover/close-batch"), {"periods": []})
        assert st == 400
        st, r = post(p("/api/carryover/open-batch"), {"periods": []})
        assert st == 400

    def test_单月结账也可跳过检查(self):
        st, r = post(p("/api/carryover/close"), {"period": "2034-04", "skip_checks": True})
        assert st == 200 and r["status"] == "closed"
        st, r = post(p("/api/carryover/open"), {"period": "2034-04"})
        assert st == 200


def _acc(code):
    for a in get(p("/api/accounts"))[1]:
        if a["code"] == code:
            return a["id"]
    raise AssertionError(f"科目不存在：{code}")
