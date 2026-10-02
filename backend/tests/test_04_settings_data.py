"""财税设置 + Excel 导入导出 + 备份恢复 测试"""
import io

import pytest
from openpyxl import load_workbook

from conftest import acc_id, api, delete, get, post, put, upload


@pytest.fixture(scope="module", autouse=True)
def keep_settings(server):
    original = get("/api/settings")[1]
    yield
    put("/api/settings", original)  # 恢复全局设置，避免影响其他模块


class TestSettings:
    def test_读取默认设置(self):
        s = get("/api/settings")[1]
        assert s["taxpayer_type"] == "small"
        assert s["accounting_standard"] == "xqy2013"
        assert s["vat_free_basis"] == "month"

    def test_修改设置并回读(self):
        assert put("/api/settings", {"income_tax_rate": "0.20"})[0] == 200
        assert get("/api/settings")[1]["income_tax_rate"] == "0.20"

    def test_修改设置影响计提所得税(self):
        # 2032-02 造一个盈利场景，税率 20% 时所得税应按 20% 计算
        assert put("/api/accounts/openings/save", {
            "year": "2032",
            "rows": [{"account_id": acc_id("1002"), "debit": 10000},
                     {"account_id": acc_id("3001"), "credit": 10000}]} )[0] == 200
        st, _ = post("/api/vouchers", {
            "date": "2032-02-10",
            "entries": [{"account_id": acc_id("1002"), "summary": "销售", "debit": 5000},
                        {"account_id": acc_id("5001"), "summary": "销售", "credit": 5000}]})
        assert st == 200
        r = get("/api/carryover/preview/income-tax?period=2032-02")[1]
        assert r["rate"] == 0.2
        assert r["amount"] == 1000  # 5000 × 20%


class TestVoucherTypes:
    def test_默认凭证类型存在(self):
        rows = get("/api/settings/voucher-types")[1]
        assert any(x["prefix"] == "记" for x in rows)

    def test_新增删除凭证类型(self):
        st, r = post("/api/settings/voucher-types", {"name": "测试凭证", "prefix": "测"})
        assert st == 200
        rows = get("/api/settings/voucher-types")[1]
        target = next(x for x in rows if x["prefix"] == "测")
        assert delete(f"/api/settings/voucher-types/{target['id']}")[0] == 200

    def test_重复前缀被拒(self):
        st, r = post("/api/settings/voucher-types", {"name": "重复", "prefix": "记"})
        assert st == 400

    def test_新前缀可用于凭证(self):
        post("/api/settings/voucher-types", {"name": "测试凭证", "prefix": "测"})
        st, r = post("/api/vouchers", {
            "date": "2032-03-05", "vtype": "测",
            "entries": [{"account_id": acc_id("560204"), "summary": "类型测试", "debit": 10},
                        {"account_id": acc_id("1002"), "summary": "类型测试", "credit": 10}]})
        assert st == 200
        assert r["voucher_no"].startswith("测-203203-")
        rows = get("/api/settings/voucher-types")[1]
        for x in rows:
            if x["prefix"] == "测":
                delete(f"/api/settings/voucher-types/{x['id']}")


class TestUnitsCurrencies:
    def test_默认计量单位(self):
        rows = get("/api/settings/units")[1]
        assert len(rows) >= 5

    def test_计量单位增删(self):
        assert post("/api/settings/units", {"name": "测试吨", "symbol": "t2"})[0] == 200
        rows = get("/api/settings/units")[1]
        target = next(x for x in rows if x["name"] == "测试吨")
        assert delete(f"/api/settings/units/{target['id']}")[0] == 200

    def test_重复计量单位被拒(self):
        st, r = post("/api/settings/units", {"name": "个"})
        assert st == 400

    def test_币种增删改(self):
        assert post("/api/settings/currencies", {"code": "jpy", "name": "日元", "rate": 0.05})[0] == 200
        rows = get("/api/settings/currencies")[1]
        target = next(x for x in rows if x["code"] == "JPY")
        assert target["rate"] == 0.05
        assert put(f"/api/settings/currencies/{target['id']}", {"rate": 0.048})[0] == 200
        rows = get("/api/settings/currencies")[1]
        assert next(x for x in rows if x["code"] == "JPY")["rate"] == 0.048
        assert delete(f"/api/settings/currencies/{target['id']}")[0] == 200

    def test_重复币种被拒(self):
        st, r = post("/api/settings/currencies", {"code": "CNY", "name": "人民币"})
        assert st == 400

    def test_默认币种存在(self):
        rows = get("/api/settings/currencies")[1]
        assert any(x["code"] == "CNY" and x["is_default"] for x in rows)


class TestCashflowSettings:
    def test_现金流量项目完整(self):
        rows = get("/api/settings/cashflow-items")[1]
        codes = {x["code"] for x in rows}
        assert {"101", "201", "401", "501", "601"} <= codes

    def test_新增删除现金流量项目(self):
        assert post("/api/settings/cashflow-items", {
            "code": "999", "name": "测试项目", "category": "operating", "direction": "D"})[0] == 200
        assert delete("/api/settings/cashflow-items/999")[0] == 200
        codes = {x["code"] for x in get("/api/settings/cashflow-items")[1]}
        assert "999" not in codes

    def test_重复项目编码被拒(self):
        st, r = post("/api/settings/cashflow-items", {"code": "101", "name": "重复"})
        assert st == 400

    def test_对照表增删改(self):
        aid = acc_id("560205")
        assert post("/api/settings/cashflow-map", {"account_id": aid, "cashflow_code": "203"})[0] == 200
        rows = get("/api/settings/cashflow-map")[1]
        target = next(x for x in rows if x["account_code"] == "560205")
        assert target["cashflow_code"] == "203"
        assert post("/api/settings/cashflow-map", {"account_id": aid, "cashflow_code": "204"})[0] == 200
        rows = get("/api/settings/cashflow-map")[1]
        target = next(x for x in rows if x["account_code"] == "560205")
        assert target["cashflow_code"] == "204"
        assert delete(f"/api/settings/cashflow-map/{target['id']}")[0] == 200

    def test_对照到不存在的项目被拒(self):
        st, r = post("/api/settings/cashflow-map",
                     {"account_id": acc_id("560205"), "cashflow_code": "888"})
        assert st == 400


class TestExport:
    def test_导出凭证明细为xlsx(self):
        st, data = api("GET", "/api/data/export/vouchers?from_period=2031-05&to_period=2031-05", raw=True)
        assert st == 200 and data[:2] == b"PK"
        wb = load_workbook(io.BytesIO(data))
        assert wb.active.max_row > 5

    def test_导出凭证明细内容正确(self):
        st, data = api("GET", "/api/data/export/vouchers?from_period=2031-05&to_period=2031-05", raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        # 借贷合计与 API 一致
        debit = sum(r[9] or 0 for r in rows)
        credit = sum(r[10] or 0 for r in rows)
        assert abs(debit - credit) < 0.01

    def test_导出总账(self):
        st, data = api("GET", "/api/data/export/book/general-ledger?period=2030-03", raw=True)
        assert st == 200 and data[:2] == b"PK"

    def test_导出余额表与API一致(self):
        st, data = api("GET", "/api/data/export/book/balance-table?period=2030-03", raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        api_rows = {r["code"]: r for r in get("/api/books/balance-table?period=2030-03")[1]["rows"]}
        for row in ws.iter_rows(min_row=2, values_only=True):
            code = str(row[0])
            if code in api_rows:
                assert row[7] == api_rows[code]["closing_credit"]
        assert st == 200

    def test_导出明细账(self):
        st, data = api("GET",
                       "/api/data/export/book/detail?account_code=1002&from_period=2030-01&to_period=2030-03",
                       raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        assert ws.max_row == 6  # 表头 + 5 笔

    def test_导出序时账(self):
        st, data = api("GET", "/api/data/export/book/journal?from_period=2030-01&to_period=2030-03", raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        assert ws.max_row == 16  # 表头 + 15 笔分录

    def test_导出多栏账(self):
        st, data = api("GET",
                       "/api/data/export/book/multi-column?account_code=5602&from_period=2030-01&to_period=2030-03",
                       raw=True)
        assert st == 200 and data[:2] == b"PK"

    def test_导出试算平衡表(self):
        st, data = api("GET", "/api/data/export/book/trial-balance?period=2030-03", raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        rows = list(ws.iter_rows(values_only=True))
        last = rows[-1]
        assert abs((last[6] or 0) - (last[7] or 0)) < 0.01  # 合计行期末借贷相等
        assert ws.max_column == 8  # 期初/本期/期末六列 + 科目两列

    def test_导出资产负债表与API一致(self):
        st, data = api("GET", "/api/reports/export/balance-sheet?period=2030-03", raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        api_rows = {x["name"]: x for x in get("/api/reports/balance-sheet?period=2030-03")[1]["rows"]}
        found = False
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] == "货币资金":
                assert row[1] == api_rows["货币资金"]["ending"] == 61660
                found = True
        assert found

    def test_导出利润表(self):
        st, data = api("GET", "/api/reports/export/income?period=2030-03&mode=month", raw=True)
        assert st == 200 and data[:2] == b"PK"

    def test_导出利润表季报(self):
        st, data = api("GET", "/api/reports/export/income?period=2030-03&mode=quarter", raw=True)
        assert st == 200 and data[:2] == b"PK"

    def test_导出现金流量表(self):
        st, data = api("GET", "/api/reports/export/cashflow?from_period=2030-01&to_period=2030-03", raw=True)
        assert st == 200 and data[:2] == b"PK"

    def test_导出凭证汇总表(self):
        st, data = api("GET", "/api/reports/export/voucher-summary?from_period=2030-01&to_period=2030-03", raw=True)
        ws = load_workbook(io.BytesIO(data)).active
        last = list(ws.iter_rows(values_only=True))[-1]
        assert last[0] == "合计" and last[1] == 6

    def test_导入模板可下载(self):
        st, data = api("GET", "/api/data/template/vouchers", raw=True)
        assert st == 200 and data[:2] == b"PK"
        ws = load_workbook(io.BytesIO(data)).active
        headers = [c.value for c in ws[1]]
        assert headers[:5] == ["凭证类别", "凭证号", "凭证日期", "附单据数", "摘要"]
        assert "科目编码" in headers and "借方金额" in headers and "贷方金额" in headers


def _xlsx_bytes(rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["日期(YYYY-MM-DD)", "凭证类型", "摘要", "科目编码", "借方金额", "贷方金额", "数量", "单位"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestImport:
    def test_导入合法凭证(self):
        data = _xlsx_bytes([
            ["2032-01-05", "记", "期初建账-现金", "1001", 5000, 0, "", ""],
            ["2032-01-05", "记", "期初建账-现金", "1002", 0, 5000, "", ""],
        ])
        st, r = upload("/api/data/import/vouchers", "import.xlsx", data)
        assert st == 200 and r["created"] == 1

    def test_导入后数据进入账簿(self):
        rows = {x["code"]: x for x in get("/api/books/balance-table?period=2032-01")[1]["rows"]}
        assert rows["1001"]["period_debit"] == 5000

    def test_科目不存在的导入被拒(self):
        data = _xlsx_bytes([["2032-01-06", "记", "错误科目", "999999", 100, 0, "", ""]])
        st, r = upload("/api/data/import/vouchers", "bad.xlsx", data)
        assert st == 400

    def test_不平衡导入被拒(self):
        data = _xlsx_bytes([["2032-01-07", "记", "不平衡", "1001", 100, 0, "", ""]])
        st, r = upload("/api/data/import/vouchers", "unbal.xlsx", data)
        assert st == 400

    def test_空日期行被跳过(self):
        data = _xlsx_bytes([
            ["", "记", "无日期", "1001", 100, 0, "", ""],
            ["2032-01-08", "记", "正常", "1001", 300, 0, "", ""],
            ["2032-01-08", "记", "正常", "1002", 0, 300, "", ""],
        ])
        st, r = upload("/api/data/import/vouchers", "mixed.xlsx", data)
        assert st == 200 and r["created"] == 1
        assert len(r["errors"]) == 1

    def test_导入自动生成凭证号(self):
        rows = get("/api/vouchers?period=2032-01")[1]["rows"]
        assert all(x["voucher_no"] for x in rows)


class TestBackup:
    def test_备份文件为SQLite(self):
        st, data = api("GET", "/api/data/backup/download", raw=True)
        assert st == 200 and data[:15] == b"SQLite format 3"
        self._backup = data

    def test_备份信息(self):
        r = get("/api/data/backup/info")[1]
        assert r["size_bytes"] > 0 and r["db_path"]

    def test_恢复备份(self):
        st, data = api("GET", "/api/data/backup/download", raw=True)
        st, r = upload("/api/data/backup/restore", "backup.db", data)
        assert st == 200 and r["ok"] is True

    def test_恢复后数据完好(self):
        rows = get("/api/accounts")[1]
        assert len(rows) >= 80
        bs = get("/api/reports/balance-sheet?period=2030-03")[1]
        assert bs["balanced"] is True

    def test_非法备份文件被拒(self):
        st, r = upload("/api/data/backup/restore", "fake.db", b"this is not a sqlite file")
        assert st == 400

    def test_备份恢复往返一致(self):
        before = get("/api/reports/balance-sheet?period=2031-05")[1]
        st, data = api("GET", "/api/data/backup/download", raw=True)
        upload("/api/data/backup/restore", "backup.db", data)
        after = get("/api/reports/balance-sheet?period=2031-05")[1]
        assert before["asset_total"] == after["asset_total"]
        assert after["balanced"] is True
