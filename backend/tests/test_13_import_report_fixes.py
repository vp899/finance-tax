"""用户反馈修复回归测试（各自跑在独立账套）

对应用户反馈：
1. 科目表导入后，科目现金流量对照表没有对应更新
2. 导入凭证后，资产负债表年初余额不对（每一年的年初余额都是 0）
3. 现金流量表从第二年开始不对（上年余额没有转进来）
"""
import io

import pytest
from openpyxl import Workbook

from conftest import delete, get, post, put, upload

ACCOUNT_HEADERS = ["科目编码", "科目名称", "方向", "默认币种", "数量核算", "计量单位",
                   "项目", "客户", "供应商", "部门", "员工", "存货"]


def _xlsx(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def p(book_id, path):
    return path + ("&" if "?" in path else "?") + f"book_id={book_id}"


def aid(book_id, code):
    for a in get(p(book_id, "/api/accounts"))[1]:
        if a["code"] == code:
            return a["id"]
    raise AssertionError(f"科目不存在：{code}")


def voucher(book_id, date, lines):
    entries = [{"account_id": aid(book_id, c), "summary": s, "debit": d, "credit": c2}
               for c, s, d, c2 in lines]
    return post(p(book_id, "/api/vouchers"),
                {"date": date, "vtype": "记", "entries": entries})


def bs_map(book_id, period):
    r = get(p(book_id, f"/api/reports/balance-sheet?period={period}"))[1]
    return {x["name"]: (x["ending"], x["beginning"]) for x in r["rows"]}, r


def cf_map(book_id, year):
    r = get(p(book_id, f"/api/reports/cashflow?year={year}"))[1]
    return {x["name"]: x["amount"] for x in r["rows"]}, r


IMPORT_ROWS = [
    ["1001", "库存现金", "借", "CNY", "否", ""],
    ["1002", "银行存款", "借", "CNY", "否", ""],
    ["100201", "工行存款", "借", "CNY", "否", ""],
    ["1122", "应收账款", "借", "CNY", "否", ""],
    ["112201", "应收-A公司", "借", "CNY", "否", ""],
    ["3001", "实收资本", "贷", "CNY", "否", ""],
    ["5602", "管理费用", "借", "CNY", "否", ""],
    ["560212", "培训费", "借", "CNY", "否", ""],
]


@pytest.fixture(scope="module", autouse=True)
def books(server):
    for bid, name, opening in (("fx13a", "对照表同步回归", ""),
                               ("fx13b", "跨年报表回归", ""),
                               ("fx13c", "期初建账回归", "2036"),
                               ("fx13d", "期初导入回归", "")):
        delete(f"/api/booksets/{bid}")
        st, r = post("/api/booksets", {"id": bid, "name": name, "opening_year": opening})
        assert st == 200, r
    # 问题1场景：科目表导入（fx13a）
    st, r = upload(p("fx13a", "/api/accounts/import"), "accounts.xlsx",
                   _xlsx(ACCOUNT_HEADERS, IMPORT_ROWS))
    assert st == 200, r
    # 问题2/3场景：只导入多年度凭证（fx13b，未录期初）
    for date, lines in (
            ("2033-01-05", [("3001", "投资", 0, 100000), ("1002", "投资", 100000, 0)]),
            ("2033-06-15", [("560204", "办公费", 2000, 0), ("1002", "付办公费", 0, 2000)]),
            ("2034-03-10", [("560204", "办公费", 3000, 0), ("1002", "付办公费", 0, 3000)]),
            ("2035-02-11", [("560204", "办公费", 1000, 0), ("1002", "付办公费", 0, 1000)])):
        assert voucher("fx13b", date, lines)[0] == 200
    yield
    for bid in ("fx13a", "fx13b", "fx13c", "fx13d"):
        delete(f"/api/booksets/{bid}")


class TestAccountImportCashflowMapSync:
    """问题1：科目表导入后，科目现金流量对照表应随科目表对应更新"""

    def _map_rows(self):
        return {x["account_code"]: x for x in get(p("fx13a", "/api/settings/cashflow-map"))[1]}

    def test_新科目自动进对照表并继承默认项目(self):
        rows = self._map_rows()
        assert rows["560212"]["cashflow_code"] == "204"   # 继承 5602 管理费用
        assert rows["112201"]["cashflow_code"] == "101"   # 继承 1122 应收账款

    def test_现金类科目不进对照表(self):
        rows = self._map_rows()
        assert "100201" not in rows   # 现金科目本身不是“对方科目”

    def test_科目默认现金流量项目同步(self):
        accs = {a["code"]: a for a in get(p("fx13a", "/api/accounts"))[1]}
        assert accs["560212"]["cashflow_code"] == "204"
        assert accs["112201"]["cashflow_code"] == "101"

    def test_导入后新增凭证自动对照用新对照(self):
        st, r = voucher("fx13a", "2033-04-10",
                        [("560212", "培训费", 100, 0), ("100201", "付培训费", 0, 100)])
        assert st == 200, r
        cash = next(e for e in r["entries"] if e["account_code"] == "100201")
        assert cash["cashflow_code"] == "204"

    def test_手工新增科目也自动补对照(self):
        st, r = post(p("fx13a", "/api/accounts"),
                     {"code": "560213", "name": "会议费", "parent_code": "5602"})
        assert st == 200, r
        rows = self._map_rows()
        assert rows["560213"]["cashflow_code"] == "204"
        # 删除科目后对照表同步清理
        assert delete(p("fx13a", f"/api/accounts/{r['id']}"))[0] == 200
        assert "560213" not in self._map_rows()

    def test_删除对照后回退上级并清除科目默认项目(self):
        rows = self._map_rows()
        assert delete(p("fx13a", f"/api/settings/cashflow-map/{rows['560212']['id']}"))[0] == 200
        accs = {a["code"]: a for a in get(p("fx13a", "/api/accounts"))[1]}
        assert accs["560212"]["cashflow_code"] is None
        st, r = voucher("fx13a", "2033-04-11",
                        [("560212", "培训费", 50, 0), ("100201", "付培训费", 0, 50)])
        assert st == 200, r
        cash = next(e for e in r["entries"] if e["account_code"] == "100201")
        assert cash["cashflow_code"] == "204"  # 回退按上级 5602 对照

    def test_科目现金流量项目可直接设置(self):
        st, _ = put(p("fx13a", f"/api/accounts/{aid('fx13a', '560212')}"),
                    {"cashflow_code": "201"})
        assert st == 200
        rows = self._map_rows()
        assert rows["560212"]["cashflow_code"] == "201"


class TestMultiYearReportsWithoutOpening:
    """问题2/3：只导入多年度凭证（未录期初）时，跨年余额必须连续累计"""

    def test_各年年初余额等于上年末(self):
        ends = {}
        for y in ("2033", "2034", "2035"):
            m, r = bs_map("fx13b", f"{y}-12")
            assert r["balanced"] is True, y
            ends[y] = m
        assert ends["2033"]["货币资金"] == (98000, 0)
        assert ends["2034"]["货币资金"] == (95000, 98000)
        assert ends["2035"]["货币资金"] == (94000, 95000)

    def test_年初余额不是零且等于上年末各合计(self):
        for prev, cur in (("2033", "2034"), ("2034", "2035")):
            e, _ = bs_map("fx13b", f"{prev}-12")
            _, r = bs_map("fx13b", f"{cur}-12")
            m = {x["name"]: (x["ending"], x["beginning"]) for x in r["rows"]}
            for name in ("货币资金", "未分配利润", "资产总计", "所有者权益合计",
                         "负债和所有者权益总计"):
                assert m[name][1] == e[name][0], f"{cur} 年 {name} 年初 ≠ {prev} 年末"

    def test_未分配利润跨年滚动(self):
        m, _ = bs_map("fx13b", "2035-12")
        assert m["未分配利润"] == (-6000, -5000)   # 三年办公费 2000/3000/1000

    def test_现金流量表期初现金结转上年余额(self):
        m1, r1 = cf_map("fx13b", "2033")
        m2, r2 = cf_map("fx13b", "2034")
        m3, r3 = cf_map("fx13b", "2035")
        assert m1["加：期初现金及现金等价物余额"] == 0
        assert m2["加：期初现金及现金等价物余额"] == 98000
        assert m3["加：期初现金及现金等价物余额"] == 95000
        for r in (r1, r2, r3):
            assert r["balanced"] is True and r["difference"] == 0

    def test_跨年区间账簿期末一致(self):
        rows = {x["code"]: x for x in
                get(p("fx13b", "/api/books/balance-table?from_period=2033-01&to_period=2035-12"))[1]["rows"]}
        assert rows["1002"]["closing_debit"] == 94000


class TestOpeningBookStillCorrect:
    """期初建账口径不受影响：录入期初的年度以其期初为准，未录入年度自动连续累计"""

    def test_录入期初与重新建账口径(self):
        bid = "fx13c"
        st, r = put(p(bid, "/api/accounts/openings/save"), {
            "year": "2036",
            "rows": [{"account_id": aid(bid, "1002"), "debit": 50000},
                     {"account_id": aid(bid, "3001"), "credit": 50000}]})
        assert st == 200, r
        assert voucher(bid, "2036-05-01",
                       [("560204", "办公费", 5000, 0), ("1002", "付办公费", 0, 5000)])[0] == 200
        assert voucher(bid, "2037-06-01",
                       [("560204", "办公费", 2000, 0), ("1002", "付办公费", 0, 2000)])[0] == 200

        m36, r36 = bs_map(bid, "2036-12")
        m37, r37 = bs_map(bid, "2037-12")
        assert r36["balanced"] is True and r37["balanced"] is True
        assert m36["货币资金"] == (45000, 50000)     # 年初 = 录入的期初
        assert m37["货币资金"] == (43000, 45000)     # 年初 = 上年末（自动连续累计）

        # 新年度录入非零期初 = 重新建账口径，以录入值为基准
        st, r = put(p(bid, "/api/accounts/openings/save"), {
            "year": "2038",
            "rows": [{"account_id": aid(bid, "1002"), "debit": 1000},
                     {"account_id": aid(bid, "3001"), "credit": 1000}]})
        assert st == 200, r
        m38, r38 = bs_map(bid, "2038-12")
        assert r38["balanced"] is True
        assert m38["货币资金"] == (1000, 1000)


OPENING_HEADERS = ["科目编码", "科目名称", "币种", "辅助核算项",
                   "项目", "项目编码", "客户", "客户编码", "供应商", "供应商编码",
                   "部门", "部门编码", "员工", "员工编码", "存货", "存货编码",
                   "规格型号", "计量单位", "方向",
                   "期初数量", "期初余额原币", "期初余额本位币",
                   "本年借方累计数量", "本年借方累计原币", "本年借方累计本位币",
                   "本年贷方累计数量", "本年贷方累计原币", "本年贷方累计本位币"]


def _opening_row(code, name, direction, base):
    return [code, name, "CNY", ""] + [""] * 12 + ["", "", direction, 0, 0, base, 0, 0, 0, 0, 0, 0]


class TestOpeningsImportRobust:
    """科目期初导入健壮性：重复导入幂等、方向必须显式"""

    def test_重复导入同一文件不叠加翻倍(self):
        rows = [_opening_row("1002", "银行存款", "借", 30000),
                _opening_row("3001", "实收资本", "贷", 30000)]
        for _ in range(2):
            st, r = upload(p("fx13d", "/api/accounts/openings/import?year=2039"),
                           "openings.xlsx", _xlsx(OPENING_HEADERS, rows))
            assert st == 200, r
        lst = get(p("fx13d", "/api/accounts/openings/list?year=2039"))[1]
        assert lst["total_debit"] == 30000 and lst["total_credit"] == 30000

    def test_方向为空时报错且不入库(self):
        rows = [_opening_row("1002", "银行存款", "", 100)]
        st, r = upload(p("fx13d", "/api/accounts/openings/import?year=2040"),
                       "openings.xlsx", _xlsx(OPENING_HEADERS, rows))
        assert st == 400 and "方向" in r["detail"]
        years = get(p("fx13d", "/api/accounts/openings/years"))[1]["years"]
        assert "2040" not in years   # 脏行未入库
