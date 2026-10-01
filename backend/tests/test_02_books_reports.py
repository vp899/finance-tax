"""账簿 + 财务报表 测试（会计年度 2030，含精确金额断言与勾稽恒等式）

场景（手工推算）：
  期初：银行存款 100000（借）/ 实收资本 100000（贷）
  2030-01：购货 1405 20000；销售 1002 20600 = 收入 20000 + 增值税 600；
          购固定资产 1601 60000；办公费 560204 1000
  2030-02：销售 1030 = 收入 1000 + 税 30
  2030-03：销售 1030 = 收入 1000 + 税 30
"""
import pytest

from conftest import acc_id, get, make_voucher, put


@pytest.fixture(scope="module", autouse=True)
def scenario(accounts):
    assert put("/api/accounts/openings/save", {
        "year": "2030",
        "rows": [{"account_id": acc_id("1002", accounts), "debit": 100000},
                 {"account_id": acc_id("3001", accounts), "credit": 100000}]} )[0] == 200
    assert make_voucher("2030-01-05", [
        ("1405", "购进商品", 20000, 0), ("2202", "购进商品", 0, 20000)])[0] == 200
    assert make_voucher("2030-01-10", [
        ("1002", "销售商品", 20600, 0), ("5001", "销售商品", 0, 20000),
        ("222101", "销售商品", 0, 600)])[0] == 200
    assert make_voucher("2030-01-12", [
        ("1601", "购置设备", 60000, 0), ("1002", "购置设备", 0, 60000)])[0] == 200
    assert make_voucher("2030-01-20", [
        ("560204", "支付办公费", 1000, 0), ("1002", "支付办公费", 0, 1000)])[0] == 200
    assert make_voucher("2030-02-10", [
        ("1002", "销售商品", 1030, 0), ("5001", "销售商品", 0, 1000),
        ("222101", "销售商品", 0, 30)])[0] == 200
    assert make_voucher("2030-03-10", [
        ("1002", "销售商品", 1030, 0), ("5001", "销售商品", 0, 1000),
        ("222101", "销售商品", 0, 30)])[0] == 200
    yield


def _gl(period):
    return {r["code"]: r for r in get(f"/api/books/general-ledger?period={period}")[1]["rows"]}


def _bs(period):
    r = get(f"/api/reports/balance-sheet?period={period}")[1]
    return r, {x["name"]: x for x in r["rows"]}


def _income(period, mode="month"):
    r = get(f"/api/reports/income?period={period}&mode={mode}")[1]
    return {x["name"]: x for x in r["rows"]}


class TestGeneralLedger:
    def test_银行存款总账精确金额(self):
        row = _gl("2030-01")["1002"]
        assert row["opening_debit"] == 100000
        assert row["period_debit"] == 20600
        assert row["period_credit"] == 61000
        assert row["closing_debit"] == 59600

    def test_管理费用总账汇总下级(self):
        assert _gl("2030-01")["5602"]["period_debit"] == 1000

    def test_存货与固定资产期末(self):
        gl = _gl("2030-01")
        assert gl["1405"]["closing_debit"] == 20000
        assert gl["1601"]["closing_debit"] == 60000

    def test_跨月累计到三月(self):
        row = _gl("2030-03")["1002"]
        assert row["period_debit"] == 1030 and row["period_credit"] == 0
        assert row["closing_debit"] == 61660

    def test_期末等于期初加发生(self):
        row = _gl("2030-01")["5001"]
        net = (row["opening_credit"] + row["period_credit"]) - (row["opening_debit"] + row["period_debit"])
        assert net == 20000 and row["closing_credit"] == 20000


class TestBalanceTable:
    def test_余额表行数完整(self):
        rows = get("/api/books/balance-table?period=2030-01")[1]["rows"]
        assert len(rows) > 50

    def test_余额表与总账一致(self):
        rows = {r["code"]: r for r in get("/api/books/balance-table?period=2030-02")[1]["rows"]}
        gl = _gl("2030-02")
        for code in ["1002", "1405", "5001", "2221"]:
            assert rows[code]["closing_debit"] == gl[code]["closing_debit"]
            assert rows[code]["closing_credit"] == gl[code]["closing_credit"]


class TestDetailLedger:
    def test_明细账逐笔与余额(self):
        r = get("/api/books/detail?account_code=1002&from_period=2030-01&to_period=2030-03")[1]
        assert r["opening"]["debit"] == 100000
        assert len(r["rows"]) == 5
        assert r["rows"][-1]["balance_debit"] == 61660

    def test_明细账逐笔运行余额连续(self):
        r = get("/api/books/detail?account_code=1002&from_period=2030-01&to_period=2030-01")[1]
        balances = [x["balance_debit"] for x in r["rows"]]
        assert balances == [120600, 60600, 59600]

    def test_明细账汇总下级(self):
        r = get("/api/books/detail?account_code=5602&from_period=2030-01&to_period=2030-01")[1]
        assert len(r["rows"]) == 1 and r["rows"][0]["account_code"] == "560204"

    def test_明细账不含下级(self):
        r = get("/api/books/detail?account_code=5602&from_period=2030-01&to_period=2030-01&rollup=false")[1]
        assert len(r["rows"]) == 0

    def test_无发生额科目明细为空(self):
        r = get("/api/books/detail?account_code=1001&from_period=2030-01&to_period=2030-03")[1]
        assert r["rows"] == []


class TestJournal:
    def test_序时账借贷合计相等(self):
        r = get("/api/books/journal?from_period=2030-01&to_period=2030-03")[1]
        assert r["total_debit"] == r["total_credit"] == 103660

    def test_序时账分录数(self):
        r = get("/api/books/journal?from_period=2030-01&to_period=2030-03")[1]
        assert len(r["rows"]) == 15

    def test_序时账按日期排序(self):
        rows = get("/api/books/journal?from_period=2030-01&to_period=2030-03")[1]["rows"]
        assert [x["date"] for x in rows] == sorted(x["date"] for x in rows)


class TestMultiColumn:
    def test_多栏账按明细科目分栏(self):
        r = get("/api/books/multi-column?account_code=5602&from_period=2030-01&to_period=2030-01")[1]
        cols = {c["code"] for c in r["columns"]}
        assert "560204" in cols
        assert r["total"]["560204"] == 1000

    def test_多栏账行数据落在对应专栏(self):
        r = get("/api/books/multi-column?account_code=5602&from_period=2030-01&to_period=2030-01")[1]
        assert r["rows"][0]["columns"]["560204"] == 1000


class TestTrialBalance:
    def test_试算平衡每个月(self):
        for p in ["2030-01", "2030-02", "2030-03"]:
            r = get(f"/api/books/trial-balance?period={p}")[1]
            assert r["balanced"] is True, p
            assert abs(r["total_debit"] - r["total_credit"]) < 0.005

    def test_试算合计为期末余额汇总(self):
        r = get("/api/books/trial-balance?period=2030-01")[1]
        # 借方：59600 + 20000 + 60000 = 139600；贷方：20000 + 600 + 100000 = 120600
        # 加上未分配利润（亏损为负）与损益类科目，整体平衡
        assert r["total_debit"] == r["total_credit"]


class TestBalanceSheet:
    def test_资产负债表平衡(self):
        raw, _ = _bs("2030-01")
        assert raw["balanced"] is True

    def test_一月资产端精确金额(self):
        _, m = _bs("2030-01")
        assert m["货币资金"]["ending"] == 59600
        assert m["存货"]["ending"] == 20000
        assert m["固定资产净额"]["ending"] == 60000
        assert m["资产总计"]["ending"] == 139600

    def test_一月负债权益端精确金额(self):
        _, m = _bs("2030-01")
        assert m["应付账款"]["ending"] == 20000
        assert m["应交税费"]["ending"] == 600
        assert m["负债合计"]["ending"] == 20600
        assert m["实收资本"]["ending"] == 100000
        assert m["未分配利润"]["ending"] == 19000
        assert m["所有者权益合计"]["ending"] == 119000

    def test_年初余额取自期初(self):
        _, m = _bs("2030-03")
        assert m["货币资金"]["beginning"] == 100000
        assert m["实收资本"]["beginning"] == 100000
        assert m["未分配利润"]["beginning"] == 0

    def test_三月累计数据(self):
        raw, m = _bs("2030-03")
        assert m["货币资金"]["ending"] == 61660
        assert m["应交税费"]["ending"] == 660
        assert m["未分配利润"]["ending"] == 21000
        assert m["资产总计"]["ending"] == 141660
        assert raw["balanced"] is True

    def test_三个月逐月平衡恒成立(self):
        for p in ["2030-01", "2030-02", "2030-03"]:
            raw, _ = _bs(p)
            assert raw["balanced"] is True, p

    def test_小计等于明细之和(self):
        _, m = _bs("2030-03")
        lines_asset = ["货币资金", "应收票据", "应收账款", "预付账款", "应收股利",
                       "应收利息", "其他应收款", "存货", "短期投资", "其他流动资产"]
        s = sum(m[n]["ending"] for n in lines_asset if n in m)
        assert abs(s - m["流动资产合计"]["ending"]) < 0.01


class TestIncomeStatement:
    def test_一月利润表精确金额(self):
        m = _income("2030-01")
        assert m["一、营业收入"]["current"] == 20000
        assert m["　　　管理费用"]["current"] == 1000
        assert m["三、利润总额（亏损以“-”号填列）"]["current"] == 19000
        assert m["四、净利润（净亏损以“-”号填列）"]["current"] == 19000

    def test_三月本月与累计(self):
        m = _income("2030-03")
        assert m["一、营业收入"]["current"] == 1000
        assert m["一、营业收入"]["ytd"] == 22000
        assert m["三、利润总额（亏损以“-”号填列）"]["ytd"] == 21000

    def test_累计等于各月之和(self):
        months = [_income(p) for p in ["2030-01", "2030-02", "2030-03"]]
        m3 = _income("2030-03")
        total = sum(x["一、营业收入"]["current"] for x in months)
        assert m3["一、营业收入"]["ytd"] == total == 22000

    def test_季报等于本季累计(self):
        q = _income("2030-03", mode="quarter")
        assert q["一、营业收入"]["quarter"] == 22000  # 一季度 = 1-3 月

    def test_季报口径为当季月份(self):
        q = _income("2030-02", mode="quarter")
        assert q["一、营业收入"]["quarter"] == 21000  # 1-2 月

    def test_利润表内部勾稽(self):
        m = _income("2030-03")
        op = (m["一、营业收入"]["ytd"] - m["　减：营业成本"]["ytd"]
              - m["　　　营业税金及附加"]["ytd"] - m["　　　销售费用"]["ytd"]
              - m["　　　管理费用"]["ytd"] - m["　　　财务费用"]["ytd"]
              + m["　加：投资收益（损失以“-”号填列）"]["ytd"])
        assert abs(op - m["二、营业利润（亏损以“-”号填列）"]["ytd"]) < 0.01
        total = m["二、营业利润（亏损以“-”号填列）"]["ytd"] + m["　加：营业外收入"]["ytd"] \
            - m["　减：营业外支出"]["ytd"]
        assert abs(total - m["三、利润总额（亏损以“-”号填列）"]["ytd"]) < 0.01


class TestCashflowStatement:
    def test_现金流项目精确金额(self):
        r = get("/api/reports/cashflow?from_period=2030-01&to_period=2030-01")[1]
        m = {x["name"]: x for x in r["rows"]}
        assert m["销售商品、提供劳务收到的现金"]["amount"] == 20600
        assert m["购建固定资产、无形资产和其他非流动资产支付的现金"]["amount"] == 60000
        assert m["支付其他与经营活动有关的现金"]["amount"] == 1000

    def test_现金流期末与账面一致(self):
        r = get("/api/reports/cashflow?from_period=2030-01&to_period=2030-01")[1]
        m = {x["name"]: x for x in r["rows"]}
        assert r["balanced"] is True
        assert m["期末现金及现金等价物余额"]["amount"] == 59600 == r["book_ending_cash"]

    def test_现金流期初取年初(self):
        r = get("/api/reports/cashflow?from_period=2030-01&to_period=2030-03")[1]
        m = {x["name"]: x for x in r["rows"]}
        assert m["加：期初现金及现金等价物余额"]["amount"] == 100000
        assert m["期末现金及现金等价物余额"]["amount"] == 61660

    def test_现金净增加额勾稽(self):
        r = get("/api/reports/cashflow?from_period=2030-01&to_period=2030-03")[1]
        m = {x["name"]: x for x in r["rows"]}
        inc = (m["经营活动现金流入小计"]["amount"] + m["投资活动现金流入小计"]["amount"]
               + m["筹资活动现金流入小计"]["amount"])
        out = (m["经营活动现金流出小计"]["amount"] + m["投资活动现金流出小计"]["amount"]
               + m["筹资活动现金流出小计"]["amount"])
        assert abs((inc - out) - m["现金及现金等价物净增加额"]["amount"]) < 0.01

    def test_季度现金流(self):
        r = get("/api/reports/cashflow?from_period=2030-01&to_period=2030-03")[1]
        m = {x["name"]: x for x in r["rows"]}
        assert m["销售商品、提供劳务收到的现金"]["amount"] == 22660


class TestVoucherSummary:
    def test_汇总表张数与平衡(self):
        r = get("/api/vouchers/summary?from_period=2030-01&to_period=2030-03")[1]
        assert r["count"] == 6
        assert r["balanced"] is True
        assert r["total_debit"] == 103660


class TestCrossCheck:
    def test_总账明细账余额表三方一致(self):
        gl = _gl("2030-03")
        det = get("/api/books/detail?account_code=1002&from_period=2030-01&to_period=2030-03")[1]
        rows = {r["code"]: r for r in get("/api/books/balance-table?period=2030-03")[1]["rows"]}
        assert gl["1002"]["closing_debit"] == det["rows"][-1]["balance_debit"] == rows["1002"]["closing_debit"]

    def test_未分配利润等于利润表净利润(self):
        _, m = _bs("2030-03")
        inc = _income("2030-03")
        assert m["未分配利润"]["ending"] == inc["四、净利润（净亏损以“-”号填列）"]["ytd"]

    def test_资产等于负债加权益每个季度末(self):
        for p in ["2030-03"]:
            raw, m = _bs(p)
            assert abs(m["资产总计"]["ending"] - (m["负债合计"]["ending"] + m["所有者权益合计"]["ending"])) < 0.01
