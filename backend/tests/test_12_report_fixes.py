"""报表口径修复回归测试（跑在独立账套 fx）

对应用户反馈：
1. 资产负债表：仅第一年正确，第二年起（年期初未更新/损益未结转）年初余额不对、表内不平
2. 现金流量表：与其它平台对不上（内部划转虚增、604/605 等项目漏计、红字被截断、期末差异）
3. 科目期初：新年度年期初自动连续累计（年期初自动更新）
"""
import pytest

from conftest import acc_id, api, delete, get, post, put

B = "book_id=fx"


def p(path):
    return path + ("&" if "?" in path else "?") + B


def aid(code):
    for a in get(p("/api/accounts"))[1]:
        if a["code"] == code:
            return a["id"]
    raise AssertionError(code)


def voucher(date, lines):
    entries = [{"account_id": aid(c), "summary": s, "debit": d, "credit": c2}
               for c, s, d, c2 in lines]
    return post(p("/api/vouchers"), {"date": date, "vtype": "记", "entries": entries})


@pytest.fixture(scope="module", autouse=True)
def book(server):
    delete("/api/booksets/fx")
    st, r = post("/api/booksets", {"id": "fx", "name": "报表修复回归", "opening_year": "2041"})
    assert st == 200, r
    # 期初：库存现金 10000 / 银行存款 100000 / 实收资本 110000
    assert put(p("/api/accounts/openings/save"), {
        "year": "2041",
        "rows": [{"account_id": aid("1001"), "debit": 10000},
                 {"account_id": aid("1002"), "debit": 100000},
                 {"account_id": aid("3001"), "credit": 110000}]})[0] == 200
    # 现金流量对照：工资 → 202，利息支出 → 604（偿还借款利息支付的现金）
    assert post(p("/api/settings/cashflow-map"),
                {"account_id": aid("560201"), "cashflow_code": "202"})[0] == 200
    assert post(p("/api/settings/cashflow-map"),
                {"account_id": aid("560301"), "cashflow_code": "604"})[0] == 200

    # 2041-01 提现（现金内部划转）：1002 → 1001
    assert voucher("2041-01-05", [("1001", "提现", 20000, 0),
                                  ("1002", "提现", 0, 20000)])[0] == 200
    # 2041-01 销售收现
    assert voucher("2041-01-10", [("1002", "收货款", 20000, 0),
                                  ("5001", "销售", 0, 20000)])[0] == 200
    # 2041-02 支付借款利息（现金流量项目 604）
    assert voucher("2041-02-10", [("560301", "付利息", 3000, 0),
                                  ("1002", "付利息", 0, 3000)])[0] == 200
    # 2041-02 发放工资（现金流量项目 202）
    assert voucher("2041-02-20", [("560201", "工资", 5000, 0),
                                  ("1002", "发工资", 0, 5000)])[0] == 200
    # 2041-03 计提折旧（非现金）
    assert voucher("2041-03-10", [("560202", "折旧", 2000, 0),
                                  ("1602", "累计折旧", 0, 2000)])[0] == 200
    # 2041-03 红字冲回上月收款（负数金额原样入库）
    assert voucher("2041-03-15", [("1002", "红冲收款", -100, 0),
                                  ("5001", "红冲销售", 0, -100)])[0] == 200
    # 2042-03 销售收现（第二年）
    assert voucher("2042-03-10", [("1002", "收货款", 30000, 0),
                                  ("5001", "销售", 0, 30000)])[0] == 200
    yield
    delete("/api/booksets/fx")


def _bs(period):
    r = get(p(f"/api/reports/balance-sheet?period={period}"))[1]
    return {x["name"]: (x["ending"], x["beginning"]) for x in r["rows"]}, r


def _cf(from_p, to_p):
    return get(p(f"/api/reports/cashflow?from_period={from_p}&to_period={to_p}"))[1]


class TestBalanceSheetCrossYear:
    def test_第一年平衡(self):
        m, r = _bs("2041-12")
        assert r["balanced"] is True
        assert m["货币资金"][0] == 121900          # 10000+20000+100000-20000+20000-3000-5000-100
        assert m["未分配利润"][0] == 9900          # 19900 收入 − 10000 费用（未结转）
        assert m["实收资本"][0] == 110000

    def test_第二年年初等于上年末(self):
        end1, _ = _bs("2041-12")
        beg2, _ = _bs("2042-01")
        for name in ("货币资金", "固定资产净额", "未分配利润", "资产总计",
                     "负债和所有者权益总计", "所有者权益合计"):
            assert beg2[name][1] == end1[name][0], name

    def test_第二年仍平衡(self):
        m, r = _bs("2042-03")
        assert r["balanced"] is True
        assert abs(m["资产总计"][0] - m["负债和所有者权益总计"][0]) < 0.01

    def test_未分配利润跨年累计(self):
        m, _ = _bs("2042-03")
        assert m["未分配利润"][1] == 9900          # 年初 = 上年末未结转损益
        assert m["未分配利润"][0] == 39900         # 期末 = 年初 + 本年 30000
        assert m["货币资金"][0] == 151900

    def test_跨年区间账簿与报表一致(self):
        rows = {x["code"]: x for x in
                get(p("/api/books/balance-table?from_period=2041-01&to_period=2042-03"))[1]["rows"]}
        assert rows["1002"]["closing_debit"] == 121900


class TestCashflowStatement:
    def test_内部划转不虚增现金流量(self):
        r = _cf("2041-01", "2041-12")
        m = {x["name"]: x["amount"] for x in r["rows"]}
        # 提现 20000 不进流入/流出
        assert m["经营活动现金流入小计"] == 19900
        assert m["经营活动现金流出小计"] == 5000

    def test_项目604不漏计(self):
        r = _cf("2041-01", "2041-12")
        m = {x["name"]: x["amount"] for x in r["rows"]}
        assert m["分配股利、利润或偿付利息支付的现金"] == 3000
        assert m["筹资活动现金流出小计"] == 3000

    def test_红字金额不被截断(self):
        r = _cf("2041-01", "2041-12")
        m = {x["name"]: x["amount"] for x in r["rows"]}
        assert m["销售商品、提供劳务收到的现金"] == 19900   # 20000 − 100
        assert m["现金及现金等价物净增加额"] == 11900       # 账面现金变动

    def test_期末现金等于账面且无差异(self):
        r = _cf("2041-01", "2041-12")
        m = {x["name"]: x["amount"] for x in r["rows"]}
        assert r["balanced"] is True
        assert r["difference"] == 0
        assert m["加：期初现金及现金等价物余额"] == 110000
        assert m["期末现金及现金等价物余额"] == 121900 == r["book_ending_cash"]

    def test_跨年区间期末现金等于账面(self):
        r = _cf("2041-01", "2042-03")
        m = {x["name"]: x["amount"] for x in r["rows"]}
        assert r["balanced"] is True and r["difference"] == 0
        assert m["期末现金及现金等价物余额"] == 151900 == r["book_ending_cash"]

    def test_月度现金流量表同样无差异(self):
        for period in ("2041-01", "2041-02", "2041-03", "2042-03"):
            r = _cf(f"{period[:4]}-01", period)
            assert r["balanced"] is True, period
            assert r["difference"] == 0, period


class TestOpeningCarryForward:
    def test_新年度年期初自动连续累计(self):
        r = get(p("/api/accounts/openings/list?year=2042"))[1]
        m = {x["code"]: x for x in r["rows"]}
        assert r["anchor_year"] == "2041"          # 年期初尚未录入 → 自动按 2041 连续累计
        assert all(x["carried"] for x in r["rows"] if x["debit"] or x["credit"])
        assert m["1001"]["debit"] == 30000
        assert m["1002"]["debit"] == 91900
        assert m["3001"]["credit"] == 110000
        assert r["balanced"] is True

    def test_录入年期初后以录入值为准(self):
        rows = [{"account_id": aid("1001"), "debit": 30000},
                {"account_id": aid("1002"), "debit": 91900},
                {"account_id": aid("1602"), "credit": 2000},
                {"account_id": aid("5001"), "credit": 19900},
                {"account_id": aid("560201"), "debit": 5000},
                {"account_id": aid("560202"), "debit": 2000},
                {"account_id": aid("560301"), "debit": 3000},
                {"account_id": aid("3001"), "credit": 110000}]
        assert put(p("/api/accounts/openings/save"),
                   {"year": "2042", "rows": rows})[0] == 200
        r = get(p("/api/accounts/openings/list?year=2042"))[1]
        assert r["anchor_year"] == "2042"
        m = {x["code"]: x for x in r["rows"]}
        assert m["1002"]["debit"] == 91900 and m["1002"]["carried"] is False
        # 录入年期初后，第二年年初仍与上年末一致（口径不变）
        end1, _ = _bs("2041-12")
        beg2, _ = _bs("2042-01")
        for name in ("货币资金", "未分配利润", "资产总计", "所有者权益合计"):
            assert beg2[name][1] == end1[name][0], name
