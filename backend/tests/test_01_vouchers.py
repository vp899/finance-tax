"""凭证管理 测试（会计年度 2026，期间 05/06/07）"""
import re

import pytest

from conftest import acc_id, api, delete, get, make_voucher, post, put


@pytest.fixture(scope="module", autouse=True)
def _need_server(accounts):
    pass


class TestCreateValidation:
    def test_合法凭证创建成功(self):
        st, r = make_voucher("2026-06-10", [
            ("560204", "办公费", 100, 0),
            ("1002", "办公费", 0, 100)])
        assert st == 200
        assert r["total_debit"] == 100 and r["total_credit"] == 100
        assert r["status"] == "posted"

    def test_凭证号格式正确(self):
        st, r = make_voucher("2026-06-11", [
            ("560205", "水电费", 200, 0),
            ("1002", "水电费", 0, 200)])
        assert st == 200
        assert re.match(r"^记-202606-\d{3}$", r["voucher_no"]), r["voucher_no"]

    def test_凭证号按月递增(self):
        st, r = make_voucher("2026-06-12", [
            ("560206", "差旅费", 300, 0),
            ("1002", "差旅费", 0, 300)])
        assert st == 200
        seq = int(r["voucher_no"].split("-")[-1])
        assert seq >= 2

    def test_借贷不平衡被拒(self):
        st, r = post("/api/vouchers", {
            "date": "2026-06-15",
            "entries": [{"account_id": acc_id("1002"), "summary": "不平", "debit": 50}]})
        assert st == 400 and "不平衡" in r["detail"]

    def test_空分录被拒(self):
        st, r = post("/api/vouchers", {"date": "2026-06-15", "entries": []})
        assert st == 400

    def test_负数金额红字原样入库(self):
        """红字（负数）金额原样保留（其它平台的负数利息收入等记法）"""
        st, r = make_voucher("2026-06-15", [
            ("1002", "红字利息收入", 1.01, 0),
            ("560301", "红字利息收入", -1.01, 0)])
        assert st == 200
        detail = get(f"/api/vouchers/{r['id']}")[1]
        e = next(x for x in detail["entries"] if x["account_code"] == "560301")
        assert e["debit"] == -1.01 and e["credit"] == 0
        assert detail["total_debit"] == 0 and detail["total_credit"] == 0

    def test_同一行借贷同时有值被拒(self):
        st, r = make_voucher("2026-06-15", [
            ("560204", "双边", 100, 100),
            ("1002", "双边", 100, 100)])
        assert st == 400

    def test_金额全零行被拒(self):
        st, r = make_voucher("2026-06-15", [
            ("560204", "零行", 0, 0),
            ("1002", "零行", 0, 0)])
        assert st == 400

    def test_非末级科目被拒(self):
        st, r = make_voucher("2026-06-15", [
            ("5602", "非末级", 100, 0),
            ("1002", "非末级", 0, 100)])
        assert st == 400

    def test_科目不存在被拒(self):
        st, r = post("/api/vouchers", {
            "date": "2026-06-15",
            "entries": [{"account_id": 999999, "summary": "x", "debit": 1},
                        {"account_id": acc_id("1002"), "summary": "x", "credit": 1}]})
        assert st == 400

    def test_多借多贷凭证(self):
        st, r = make_voucher("2026-06-20", [
            ("560201", "发工资", 5000, 0),
            ("560204", "办公费", 800, 0),
            ("1002", "支付", 0, 5000),
            ("1001", "支付", 0, 800)])
        assert st == 200
        assert len(r["entries"]) == 4

    def test_三位小数金额被拒(self):
        st, r = make_voucher("2026-06-15", [
            ("560204", "小数", 100.005, 0),
            ("1002", "小数", 0, 100.005)])
        assert st == 400


class TestVoucherQuery:
    def test_按期间查询(self):
        st, r = get("/api/vouchers?period=2026-06&page=1&size=50")
        assert st == 200
        assert r["total"] >= 3
        assert all(v["period"] == "2026-06" for v in r["rows"])

    def test_分页字段正确(self):
        st, r = get("/api/vouchers?period=2026-06&page=1&size=2")
        assert st == 200
        assert len(r["rows"]) == 2 and r["size"] == 2 and r["page"] == 1

    def test_按状态过滤(self):
        st, r = get("/api/vouchers?period=2026-06&status=posted")
        assert st == 200
        assert all(v["status"] == "posted" for v in r["rows"])

    def test_搜索关键字(self):
        st, r = get("/api/vouchers?period=2026-06&q=差旅")
        assert st == 200
        assert r["total"] >= 1

    def test_凭证详情含科目编码(self):
        vid = get("/api/vouchers?period=2026-06")[1]["rows"][-1]["id"]
        st, r = get(f"/api/vouchers/{vid}")
        assert st == 200
        assert all(e["account_code"] and e["account_name"] for e in r["entries"])

    def test_凭证不存在返回404(self):
        st, r = get("/api/vouchers/999999")
        assert st == 404


class TestVoucherUpdate:
    def test_修改分录金额(self):
        vid = get("/api/vouchers?period=2026-06&q=差旅")[1]["rows"][0]["id"]
        st, r = put(f"/api/vouchers/{vid}", {
            "date": "2026-06-12",
            "entries": [
                {"account_id": acc_id("560206"), "summary": "差旅费-改", "debit": 350},
                {"account_id": acc_id("1002"), "summary": "差旅费-改", "credit": 350}]})
        assert st == 200
        assert r["total_debit"] == 350

    def test_修改成不平衡被拒(self):
        vid = get("/api/vouchers?period=2026-06&q=差旅")[1]["rows"][0]["id"]
        st, r = put(f"/api/vouchers/{vid}", {
            "date": "2026-06-12",
            "entries": [{"account_id": acc_id("560206"), "summary": "x", "debit": 100}]})
        assert st == 400

    def test_作废与恢复(self):
        vid = get("/api/vouchers?period=2026-06&q=水电")[1]["rows"][0]["id"]
        st, r = post(f"/api/vouchers/{vid}/void")
        assert st == 200 and r["status"] == "voided"
        st, r = post(f"/api/vouchers/{vid}/void")
        assert st == 200 and r["status"] == "posted"

    def test_作废凭证不计入账簿(self):
        vid = get("/api/vouchers?period=2026-06&q=水电")[1]["rows"][0]["id"]
        post(f"/api/vouchers/{vid}/void")
        rows = get("/api/books/general-ledger?period=2026-06")[1]["rows"]
        admin = next(r for r in rows if r["code"] == "5602")
        # 水电费 200 已作废：管理费用剩 100 + 350 + 5000 + 800 = 6250
        assert admin["period_debit"] == 6250
        post(f"/api/vouchers/{vid}/void")  # 恢复

    def test_复制凭证(self):
        vid = get("/api/vouchers?period=2026-06&q=水电")[1]["rows"][0]["id"]
        st, r = post(f"/api/vouchers/{vid}/copy")
        assert st == 200
        assert r["voucher_no"] != "" and len(r["entries"]) == 2


class TestSuggest:
    def test_科目智能补全(self):
        st, r = get("/api/vouchers/suggest?q=yhck")
        assert st == 200
        assert any(a["code"] == "1002" for a in r["accounts"])

    def test_摘要智能补全(self):
        st, r = get("/api/vouchers/suggest?q=办公费")
        assert st == 200
        assert any("办公费" in s for s in r["summaries"])

    def test_补全带余额(self):
        st, r = get("/api/vouchers/suggest?q=1002")
        assert st == 200
        assert "balance" in r["accounts"][0]


class TestCashflowAutoFill:
    def test_现金分录自动补现金流量项目(self):
        st, r = make_voucher("2026-07-05", [
            ("560204", "自动对照测试", 100, 0),
            ("1002", "自动对照测试", 0, 100)])
        assert st == 200
        cash_line = next(e for e in r["entries"] if e["account_code"] == "1002")
        assert cash_line["cashflow_code"] == "204"  # 560204 上卷到 5602 -> 支付其他

    def test_现金流入自动对照收入科目(self):
        st, r = make_voucher("2026-07-06", [
            ("1002", "销售收现", 1000, 0),
            ("5001", "销售收现", 0, 1000)])
        assert st == 200
        cash_line = next(e for e in r["entries"] if e["account_code"] == "1002")
        assert cash_line["cashflow_code"] == "101"

    def test_修改对照表后自动对照变化(self):
        aid = acc_id("560204")
        st, _ = post("/api/settings/cashflow-map", {"account_id": aid, "cashflow_code": "201"})
        assert st == 200
        st, r = make_voucher("2026-07-07", [
            ("560204", "对照变更测试", 50, 0),
            ("1002", "对照变更测试", 0, 50)])
        cash_line = next(e for e in r["entries"] if e["account_code"] == "1002")
        assert cash_line["cashflow_code"] == "201"
        # 清除对照，恢复按上级科目回退
        rows = get("/api/settings/cashflow-map")[1]
        target = next(x for x in rows if x["account_code"] == "560204")
        delete(f"/api/settings/cashflow-map/{target['id']}")
        st, r = make_voucher("2026-07-08", [
            ("560204", "对照恢复测试", 50, 0),
            ("1002", "对照恢复测试", 0, 50)])
        cash_line = next(e for e in r["entries"] if e["account_code"] == "1002")
        assert cash_line["cashflow_code"] == "204"


class TestVoucherSummary:
    def test_凭证汇总表借贷平衡(self):
        st, r = get("/api/vouchers/summary?from_period=2026-06&to_period=2026-06")
        assert st == 200
        assert r["balanced"] is True
        assert r["count"] >= 3

    def test_凭证汇总表按类型分组(self):
        st, r = get("/api/vouchers/summary?from_period=2026-06&to_period=2026-06")
        assert any(x["vtype"] == "记" for x in r["rows"])
