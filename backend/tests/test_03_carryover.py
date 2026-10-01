"""结转 / 反结转 / 结账 测试（会计年度 2031，顺序场景）

场景（手工推算）：
  期初：银行存款 300000（借）/ 实收资本 300000（贷）
  2031-05：购货 20000；销售 51500 = 收入 50000 + 税 1500；购固定资产 120000；购无形资产 60000
  固定资产 120000/残值5%/120月 → 月折旧 950；无形资产 60000/120月 → 月摊销 500
  计提：销售成本 20000、工资 3000、税金 180（基数1500）
  累计利润总额 = 50000-20000-180-(3000+950+500) = 25370 → 所得税 6342.5 → 净利润 19027.5
"""
import pytest

from conftest import acc_id, get, make_voucher, post, put


@pytest.fixture(scope="module", autouse=True)
def scenario(accounts):
    assert put("/api/accounts/openings/save", {
        "year": "2031",
        "rows": [{"account_id": acc_id("1002", accounts), "debit": 300000},
                 {"account_id": acc_id("3001", accounts), "credit": 300000}]} )[0] == 200
    assert make_voucher("2031-05-05", [
        ("1405", "购进商品", 20000, 0), ("2202", "购进商品", 0, 20000)])[0] == 200
    assert make_voucher("2031-05-10", [
        ("1002", "销售商品", 51500, 0), ("5001", "销售商品", 0, 50000),
        ("222101", "销售商品", 0, 1500)])[0] == 200
    assert make_voucher("2031-05-12", [
        ("1601", "购置设备", 120000, 0), ("1002", "购置设备", 0, 120000)])[0] == 200
    assert make_voucher("2031-05-12", [
        ("1701", "购置软件", 60000, 0), ("1002", "购置软件", 0, 60000)])[0] == 200
    assert post("/api/carryover/assets/fixed", {
        "name": "生产设备", "original_value": 120000, "residual_rate": 0.05,
        "life_months": 120, "expense_account_code": "560202"} )[0] == 200
    assert post("/api/carryover/assets/intangible", {
        "name": "管理软件", "original_value": 60000, "amort_months": 120,
        "expense_account_code": "560203"} )[0] == 200
    yield


def _income(period="2031-05", mode="month"):
    return {x["name"]: x for x in get(f"/api/reports/income?period={period}&mode={mode}")[1]["rows"]}


def _bs(period="2031-05"):
    r = get(f"/api/reports/balance-sheet?period={period}")[1]
    return r, {x["name"]: x for x in r["rows"]}


class TestDepreciationAmortization:
    def test_折旧预览按资产计算(self):
        r = get("/api/carryover/preview/depreciation?period=2031-05")[1]
        assert r["total"] == 950
        assert len(r["items"]) == 1

    def test_计提折旧(self):
        st, r = post("/api/carryover/depreciation", {"period": "2031-05"})
        assert st == 200 and r["amount"] == 950
        assert r["voucher_no"]

    def test_摊销预览(self):
        r = get("/api/carryover/preview/amortization?period=2031-05")[1]
        assert r["total"] == 500

    def test_摊销无形资产(self):
        st, r = post("/api/carryover/amortization", {"period": "2031-05"})
        assert st == 200 and r["amount"] == 500

    def test_折旧生成凭证分录正确(self):
        vid = [x for x in get("/api/carryover/records?period=2031-05")[1]
               if x["kind"] == "depreciation"][0]["voucher_id"]
        v = get(f"/api/vouchers/{vid}")[1]
        codes = {e["account_code"]: e for e in v["entries"]}
        assert codes["560202"]["debit"] == 950
        assert codes["1602"]["credit"] == 950

    def test_折旧预览可重复读取幂等(self):
        r = get("/api/carryover/preview/depreciation?period=2031-05")[1]
        assert r["total"] == 950  # 预览不产生副作用


class TestSalesCostSalary:
    def test_销售成本预览(self):
        r = get("/api/carryover/preview/sales_cost?period=2031-05")[1]
        assert r["period_income"] == 50000
        assert r["expense_code"] == "5401" and r["credit_code"] == "1405"

    def test_结转销售成本(self):
        st, r = post("/api/carryover/sales_cost", {"period": "2031-05", "amount": 20000})
        assert st == 200 and r["amount"] == 20000

    def test_销售成本金额为零被拒(self):
        st, r = post("/api/carryover/sales_cost", {"period": "2031-05", "amount": 0})
        assert st == 400

    def test_计提工资(self):
        st, r = post("/api/carryover/salary", {"period": "2031-05", "amount": 3000})
        assert st == 200 and r["amount"] == 3000

    def test_工资预览带参考金额(self):
        r = get("/api/carryover/preview/salary?period=2031-06")[1]
        assert r["suggested_amount"] == 3000  # 上期（2031-05）计提
        r0 = get("/api/carryover/preview/salary?period=2031-05")[1]
        assert r0["suggested_amount"] == 0  # 当期尚无历史


class TestTaxAndIncomeTax:
    def test_税金预览按增值税基数(self):
        r = get("/api/carryover/preview/tax?period=2031-05")[1]
        assert r["vat_base"] == 1500
        assert r["city_tax"] == 105
        assert r["edu_tax"] == 45
        assert r["local_edu_tax"] == 30

    def test_计提税金(self):
        st, r = post("/api/carryover/tax", {"period": "2031-05"})
        assert st == 200 and r["amount"] == 180

    def test_税金基数为零被拒(self):
        st, r = post("/api/carryover/tax", {"period": "2031-05", "vat_base": 0})
        assert st == 400

    def test_所得税预览(self):
        r = get("/api/carryover/preview/income-tax?period=2031-05")[1]
        assert r["total_profit_ytd"] == 25370
        assert r["amount"] == 6342.5

    def test_结转损益前结账失败(self):
        st, r = post("/api/carryover/close", {"period": "2031-05"})
        assert st == 400

    def test_计提所得税(self):
        st, r = post("/api/carryover/income_tax", {"period": "2031-05"})
        assert st == 200 and r["amount"] == 6342.5

    def test_重复计提所得税为零被拒(self):
        st, r = post("/api/carryover/income_tax", {"period": "2031-05"})
        assert st == 400


class TestProfitCarryover:
    def test_损益结转预览(self):
        r = get("/api/carryover/preview/profit?period=2031-05")[1]
        assert r["total_income"] == 50000
        assert r["total_expense"] == 30972.5
        assert r["net_profit"] == 19027.5

    def test_结转本期损益(self):
        st, r = post("/api/carryover/profit", {"period": "2031-05"})
        assert st == 200 and r["amount"] == 50000

    def test_重复结转损益被拒(self):
        st, r = post("/api/carryover/profit", {"period": "2031-05"})
        assert st == 400

    def test_结转后利润表不受结转分录影响(self):
        m = _income()
        assert m["一、营业收入"]["ytd"] == 50000
        assert m["　减：营业成本"]["ytd"] == 20000
        assert m["四、净利润（净亏损以“-”号填列）"]["ytd"] == 19027.5

    def test_结转后资产负债表平衡(self):
        raw, m = _bs()
        assert raw["balanced"] is True
        assert m["未分配利润"]["ending"] == 19027.5
        assert m["货币资金"]["ending"] == 171500
        assert m["存货"]["ending"] == 0
        assert m["固定资产净额"]["ending"] == 119050
        assert m["无形资产"]["ending"] == 59500

    def test_结转后试算平衡(self):
        r = get("/api/books/trial-balance?period=2031-05")[1]
        assert r["balanced"] is True


class TestReverse:
    def test_反结转销售成本(self):
        rec = next(x for x in get("/api/carryover/records?period=2031-05")[1]
                   if x["kind"] == "sales_cost")
        st, r = post(f"/api/carryover/reverse/{rec['id']}")
        assert st == 200 and r["kind"] == "结转销售成本"

    def test_反结转后成本回退(self):
        m = _income()
        assert m["　减：营业成本"]["ytd"] == 0

    def test_反结转后存货回补且报表平衡(self):
        raw, m = _bs()
        assert m["存货"]["ending"] == 20000
        assert raw["balanced"] is True
        assert m["未分配利润"]["ending"] == 39027.5  # 19027.5 + 回退成本 20000

    def test_重复反结转被拒(self):
        rec = next(x for x in get("/api/carryover/records?period=2031-05")[1]
                   if x["kind"] == "sales_cost")
        st, r = post(f"/api/carryover/reverse/{rec['id']}")
        assert st == 400

    def test_反结转记录状态(self):
        rec = next(x for x in get("/api/carryover/records?period=2031-05")[1]
                   if x["kind"] == "sales_cost")
        assert rec["status"] == "reversed"

    def test_重新结转后成本恢复(self):
        st, r = post("/api/carryover/sales_cost", {"period": "2031-05", "amount": 20000})
        assert st == 200
        assert _income()["　减：营业成本"]["ytd"] == 20000

    def test_反结转后试算仍平衡(self):
        assert get("/api/books/trial-balance?period=2031-05")[1]["balanced"] is True


class TestVatFree:
    def test_免税预览未达起征点可用(self):
        assert make_voucher("2031-06-10", [
            ("1002", "销售商品", 3090, 0), ("5001", "销售商品", 0, 3000),
            ("222101", "销售商品", 0, 90)])[0] == 200
        r = get("/api/carryover/preview/vat-free?period=2031-06")[1]
        assert r["sales_month"] == 3000
        assert r["eligible"] is True
        assert r["vat_amount"] == 90

    def test_免交增值税执行(self):
        st, r = post("/api/carryover/vat_free", {"period": "2031-06"})
        assert st == 200 and r["amount"] == 90

    def test_免税后应交增值税科目清零(self):
        gl = {x["code"]: x for x in get("/api/books/general-ledger?period=2031-06")[1]["rows"]}
        # 6 月销项 90 被免征转出：本期借方 = 本期贷方 = 90
        assert gl["222101"]["period_debit"] == 90
        assert gl["222101"]["period_credit"] == 90
        assert gl["5301"]["closing_credit"] == 90  # 转入营业外收入
        # 5 月尚未免征的 1500 仍挂账（各期独立处理）
        assert gl["222101"]["closing_credit"] == 1500

    def test_超过起征点不可免征(self):
        assert make_voucher("2031-07-10", [
            ("1002", "大额销售", 206000, 0), ("5001", "大额销售", 0, 200000),
            ("222101", "大额销售", 0, 6000)])[0] == 200
        r = get("/api/carryover/preview/vat-free?period=2031-07")[1]
        assert r["eligible"] is False
        st, _ = post("/api/carryover/vat_free", {"period": "2031-07"})
        assert st == 400


class TestClosePeriod:
    def test_草稿凭证阻塞结账(self):
        st, r = post("/api/vouchers", {
            "date": "2031-08-10", "status": "draft",
            "entries": [{"account_id": acc_id("560204"), "summary": "草稿", "debit": 10},
                        {"account_id": acc_id("1002"), "summary": "草稿", "credit": 10}]})
        assert st == 200 and r["status"] == "draft"
        st, r = post("/api/carryover/close", {"period": "2031-08"})
        assert st == 400

    def test_损益未结平结账失败(self):
        st, r = post("/api/carryover/close", {"period": "2031-06"})
        assert st == 400

    def test_强制结账成功(self):
        st, r = post("/api/carryover/close", {"period": "2031-06", "force": True})
        assert st == 200 and r["status"] == "closed"

    def test_结账后新增凭证被拒(self):
        st, r = make_voucher("2031-06-20", [
            ("560204", "结账后", 10, 0), ("1002", "结账后", 0, 10)])
        assert st == 400

    def test_结账后修改凭证被拒(self):
        vid = get("/api/vouchers?period=2031-06")[1]["rows"][0]["id"]
        st, r = put(f"/api/vouchers/{vid}", {
            "date": "2031-06-10",
            "entries": [{"account_id": acc_id("560204"), "summary": "改", "debit": 10},
                        {"account_id": acc_id("1002"), "summary": "改", "credit": 10}]})
        assert st == 400

    def test_结账后反结转被拒(self):
        rec = next(x for x in get("/api/carryover/records?period=2031-06")[1]
                   if x["kind"] == "vat_free")
        st, r = post(f"/api/carryover/reverse/{rec['id']}")
        assert st == 400

    def test_反结账(self):
        st, r = post("/api/carryover/open", {"period": "2031-06"})
        assert st == 200 and r["status"] == "open"

    def test_反结账后可继续记账(self):
        st, r = make_voucher("2031-06-22", [
            ("560204", "反结账后", 10, 0), ("1002", "反结账后", 0, 10)])
        assert st == 200

    def test_损益结平后正常结账(self):
        st, r = post("/api/carryover/close", {"period": "2031-05"})
        assert st == 200 and r["status"] == "closed"

    def test_结账期间状态可查询(self):
        rows = get("/api/carryover/periods")[1]
        m = {x["period"]: x["status"] for x in rows}
        assert m["2031-05"] == "closed"

    def test_结账后恢复开启以免影响后续(self):
        assert post("/api/carryover/open", {"period": "2031-05"})[0] == 200
