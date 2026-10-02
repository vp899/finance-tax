"""明细账导入 / 导出 + 科目期初年份设置 测试（跑在独立账套 t08 内）"""
import io

import pytest
from openpyxl import Workbook, load_workbook

from conftest import api, delete, get, post, put, upload

HEADERS = ["序号", "科目编码", "科目", "日期", "凭证号", "摘要", "借方", "贷方", "方向", "余额"]
B = "book_id=t08"


def p(path):
    return path + ("&" if "?" in path else "?") + B


def xlsx(rows, headers=HEADERS):
    wb = Workbook()
    ws = wb.active
    ws.title = "明细账"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def raw_rows(data: bytes):
    ws = load_workbook(io.BytesIO(data)).active
    return [list(r) for r in ws.iter_rows(values_only=True)]


# 完整（借贷齐全）的示例明细账：2 张凭证 + 4 行期初
FULL_ROWS = [
    [1, "1001", "库存现金", "2021-01", "期初余额", "", None, None, "平", None],
    [2, "1001", "库存现金", "2021-01-31", "记-001", "提现备用金", 5000.00, None, "借", 5000.00],
    [3, "1001", "库存现金", "2021-01-31", "记-002", "购买办公用品", None, 300.00, "贷", 4700.00],
    [4, "1002", "银行存款", "2021-01", "期初余额", "", 10000.00, None, "借", 10000.00],
    [5, "1002", "银行存款", "2021-01-31", "记-001", "提现备用金", None, 5000.00, "贷", 5000.00],
    [6, "3001", "实收资本", "2021-01", "期初余额", "", None, 10000.00, "贷", 10000.00],
    [7, "5602", "管理费用", "2021-01", "期初余额", "", None, None, "平", None],
    [8, "5602", "管理费用", "2021-01-31", "记-002", "购买办公用品", 300.00, None, "借", 300.00],
]

# 只含 1001（库存现金）一侧的明细账：凭证缺对方科目（2021-02，避免与完整文件同号）
ONE_SIDE_ROWS = [
    [1, "1001", "库存现金", "2021-02-28", "记-101", "提现备用金", 5000.00, None, None, None],
    [2, "1001", "库存现金", "2021-02-28", "记-102", "购买办公用品", None, 300.00, None, None],
]

# 补齐对方科目（1002 / 5602 一侧）
OTHER_SIDE_ROWS = [
    [1, "1002", "银行存款", "2021-02-28", "记-101", "提现备用金", None, 5000.00, None, None],
    [2, "5602", "管理费用", "2021-02-28", "记-102", "购买办公用品", 300.00, None, None, None],
]


@pytest.fixture(scope="module", autouse=True)
def book(server):
    delete(f"/api/booksets/t08")
    st, r = post("/api/booksets", {"id": "t08", "name": "明细账测试账套", "opening_year": "2033"})
    assert st == 200
    yield
    delete("/api/booksets/t08")


class TestTemplate:
    def test_模板可下载(self):
        st, data = api("GET", "/api/data/template/detail-ledger", raw=True)
        assert st == 200 and data[:2] == b"PK"

    def test_模板导入可跑通(self):
        # 模板单独跑在临时账套，避免影响后续用例数据
        delete("/api/booksets/t08tpl")
        assert post("/api/booksets", {"id": "t08tpl", "name": "模板测试"})[0] == 200
        try:
            st, data = api("GET", "/api/data/template/detail-ledger", raw=True)
            st, r = upload("/api/data/import/detail-ledger?book_id=t08tpl", "tpl.xlsx", data)
            assert st == 200
            assert r["created_vouchers"] >= 1
            assert r["draft_vouchers"] == 0
            assert r["errors"] == []
        finally:
            delete("/api/booksets/t08tpl")


class TestImportExport:
    def test_导入完整明细账(self):
        st, r = upload(p("/api/data/import/detail-ledger"), "full.xlsx", xlsx(FULL_ROWS))
        assert st == 200, r
        assert r["rows"] == 8
        assert r["created_vouchers"] == 2
        assert r["draft_vouchers"] == 0
        assert r["errors"] == []
        assert r["opening_rows"] == 4
        assert r["opening_balanced"] is True
        assert r["opening_year"] == "2021"
        assert r["opening_years"] == ["2021"]

    def test_导入后凭证号保留原始编号(self):
        rows = get(p("/api/vouchers?from_period=2021-01&to_period=2021-12&size=50"))[1]["rows"]
        nos = {v["source_no"] for v in rows}
        assert {"记-001", "记-002"} <= nos
        v = next(x for x in rows if x["source_no"] == "记-001")
        assert v["status"] == "posted" and v["source"] == "import"
        assert v["total_debit"] == 5000 and v["total_credit"] == 5000

    def test_期初余额写入科目期初(self):
        rows = get(p("/api/accounts/openings/list?year=2021"))[1]
        by_code = {r["code"]: r for r in rows["rows"]}
        assert by_code["1002"]["debit"] == 10000
        assert by_code["3001"]["credit"] == 10000
        assert rows["balanced"] is True

    def test_期初年份设置随导入更新(self):
        st, y = get(p("/api/accounts/openings/years"))
        assert y["opening_year"] == "2021"
        assert y["years"] == ["2021"]

    def test_重复导入幂等(self):
        st, r = upload(p("/api/data/import/detail-ledger"), "full.xlsx", xlsx(FULL_ROWS))
        assert st == 200
        assert r["created_vouchers"] == 0
        assert r["skipped_vouchers"] == 2
        rows = get(p("/api/vouchers?from_period=2021-01&to_period=2021-12&size=50"))[1]
        assert rows["total"] == 2

    def test_导出格式与内容(self):
        st, data = api("GET", p("/api/data/export/detail-ledger"
                                "?from_period=2021-01&to_period=2021-12"), raw=True)
        assert st == 200
        rows = raw_rows(data)
        assert list(rows[0]) == HEADERS
        # 序号连续
        assert [r[0] for r in rows[1:]] == list(range(1, len(rows)))
        body = [(str(r[1]), str(r[3]), str(r[4]), (r[5] or ""), r[6], r[7], r[8], r[9])
                for r in rows[1:]]
        expect = [
            ("1001", "2021-01", "期初余额", "", None, None, "平", None),
            ("1001", "2021-01-31", "记-001", "提现备用金", 5000, None, "借", 5000),
            ("1001", "2021-01-31", "记-002", "购买办公用品", None, 300, "借", 4700),
            ("1002", "2021-01", "期初余额", "", 10000, None, "借", 10000),
            ("1002", "2021-01-31", "记-001", "提现备用金", None, 5000, "借", 5000),
            ("3001", "2021-01", "期初余额", "", None, 10000, "贷", 10000),
            ("5602", "2021-01", "期初余额", "", None, None, "平", None),
            ("5602", "2021-01-31", "记-002", "购买办公用品", 300, None, "借", 300),
        ]
        assert body == expect

    def test_导出指定科目(self):
        st, data = api("GET", p("/api/data/export/detail-ledger"
                                "?account_code=1001&from_period=2021-01&to_period=2021-12"), raw=True)
        rows = raw_rows(data)
        assert {str(r[1]) for r in rows[1:]} == {"1001"}
        assert rows[1][4] == "期初余额"
        assert rows[2][9] == 5000     # 余额滚动
        assert rows[3][9] == 4700

    def test_导出导入再导出往返一致(self):
        st, data = api("GET", p("/api/data/export/detail-ledger"
                                "?from_period=2021-01&to_period=2021-12"), raw=True)
        st, r = upload(p("/api/data/import/detail-ledger"), "round.xlsx", data)
        assert st == 200
        assert r["created_vouchers"] == 0 and r["skipped_vouchers"] == 2
        st, data2 = api("GET", p("/api/data/export/detail-ledger"
                                 "?from_period=2021-01&to_period=2021-12"), raw=True)
        assert raw_rows(data) == raw_rows(data2)

    def test_明细账查询与导入一致(self):
        d = get(p("/api/books/detail?account_code=1001&from_period=2021-01&to_period=2021-12"))[1]
        assert d["opening"] == {"debit": 0, "credit": 0} or d["opening"]["debit"] == 0
        assert len(d["rows"]) == 2
        assert d["rows"][0]["source_no"] == "记-001"
        assert d["rows"][0]["balance_debit"] == 5000
        assert d["rows"][1]["balance_credit"] == 0 and d["rows"][1]["balance_debit"] == 4700


class TestSingleSideImport:
    def test_单侧导入生成草稿并提示(self):
        st, r = upload(p("/api/data/import/detail-ledger"), "one.xlsx", xlsx(ONE_SIDE_ROWS))
        assert st == 200
        assert r["created_vouchers"] == 2
        assert r["draft_vouchers"] == 2
        assert len(r["unbalanced"]) == 2
        assert any("草稿" in w for w in r["warnings"])
        rows = get(p("/api/vouchers?from_period=2021-01&to_period=2021-12&size=50"))[1]["rows"]
        drafts = [v for v in rows if v["status"] == "draft"]
        assert len(drafts) == 2
        # 草稿不进入账簿：明细账仍只有 1 月的 2 行
        d = get(p("/api/books/detail?account_code=1001&from_period=2021-01&to_period=2021-12"))[1]
        assert len(d["rows"]) == 2

    def test_补导对方科目后自动转正式(self):
        st, r = upload(p("/api/data/import/detail-ledger"), "other.xlsx", xlsx(OTHER_SIDE_ROWS))
        assert st == 200
        assert r["created_vouchers"] == 0
        assert r["merged_vouchers"] == 2
        assert r["draft_vouchers"] == 0
        rows = get(p("/api/vouchers?from_period=2021-01&to_period=2021-12&size=50"))[1]["rows"]
        assert all(v["status"] == "posted" for v in rows)
        v = next(x for x in rows if x["source_no"] == "记-001")
        assert v["total_debit"] == 5000 and v["total_credit"] == 5000
        assert v["entry_count"] == 2

    def test_转正式后进入账簿(self):
        d = get(p("/api/books/detail?account_code=1001&from_period=2021-01&to_period=2021-12"))[1]
        assert len(d["rows"]) == 4          # 1 月 2 行 + 2 月补齐后的 2 行
        assert d["rows"][-1]["balance_debit"] == 9400  # 5000-300+5000-300


class TestOpeningYearSetting:
    def test_设置期初年份(self):
        st, r = put(p("/api/accounts/openings/set-year"), {"year": "2033"})
        assert st == 200 and r["opening_year"] == "2033"
        y = get(p("/api/accounts/openings/years"))[1]
        assert y["opening_year"] == "2033"
        assert y["configured"] == "2033"

    def test_期初年份格式校验(self):
        assert put(p("/api/accounts/openings/set-year"), {"year": "203"})[0] == 400
        assert put(p("/api/accounts/openings/set-year"), {"year": "abcd"})[0] == 400
        assert put(p("/api/settings"), {"opening_year": "3000"})[0] == 400
        assert put(p("/api/settings"), {"opening_year": "2033"})[0] == 200

    def test_科目期初按设置年份展示(self):
        st, r = put(p("/api/accounts/openings/save"), {
            "rows": [{"account_id": _acc("1002"), "debit": 1},
                     {"account_id": _acc("3001"), "credit": 1}]})
        assert st == 200
        lst = get(p("/api/accounts/openings/list"))[1]   # 不带 year → 用设置年份
        assert lst["year"] == "2033"
        assert lst["total_debit"] == 1 and lst["total_credit"] == 1

    def test_多年度期初共存(self):
        st, r = put(p("/api/accounts/openings/save"), {
            "year": "2034",
            "rows": [{"account_id": _acc("1002"), "debit": 2},
                     {"account_id": _acc("3001"), "credit": 2}]})
        assert st == 200
        y = get(p("/api/accounts/openings/years"))[1]
        assert set(y["years"]) >= {"2021", "2033", "2034"}


def _acc(code: str) -> int:
    for a in get(p("/api/accounts"))[1]:
        if a["code"] == code:
            return a["id"]
    raise AssertionError(f"科目不存在：{code}")


class TestImportErrors:
    def test_未知科目自动创建(self):
        rows = [
            [1, "1001", "库存现金", "2022-01", "期初余额", "", None, None, "平", None],
            [2, "1001", "库存现金", "2022-01-31", "记-101", "运费", None, 50.00, "贷", 50.00],
            [3, "660199", "销售费用-运费", "2022-01-31", "记-101", "运费", 50.00, None, "借", 50.00],
        ]
        st, r = upload(p("/api/data/import/detail-ledger"), "new.xlsx", xlsx(rows))
        assert st == 200
        assert any("660199" in c for c in r["created_accounts"])
        codes = {a["code"] for a in get(p("/api/accounts"))[1]}
        assert "660199" in codes

    def test_缺日期或凭证号或金额报错(self):
        rows = [
            [1, "1001", "库存现金", "", "记-201", "缺日期", 10, None, None, None],
            [2, "1001", "库存现金", "2022-02-28", "", "缺凭证号", 10, None, None, None],
            [3, "1001", "库存现金", "2022-02-28", "记-201", "零金额", 0, 0, None, None],
            [4, "1001", "库存现金", "2022-02-28", "记-201", "提现", 10, None, None, None],
            [5, "1002", "银行存款", "2022-02-28", "记-201", "提现", None, 10, None, None],
        ]
        st, r = upload(p("/api/data/import/detail-ledger"), "bad.xlsx", xlsx(rows))
        assert st == 200
        assert len(r["errors"]) == 3
        assert any("日期无效" in e for e in r["errors"])
        assert any("凭证号为空" in e for e in r["errors"])
        assert any("同时为零" in e for e in r["errors"])
        assert r["created_vouchers"] == 1

    def test_余额列不符给出警告(self):
        rows = [
            [1, "1001", "库存现金", "2022-03-01", "记-301", "提现", 100.00, None, "借", 100.00],
            [2, "1002", "银行存款", "2022-03-01", "记-301", "提现", None, 100.00, "贷", 999.00],
        ]
        st, r = upload(p("/api/data/import/detail-ledger"), "warn.xlsx", xlsx(rows))
        assert st == 200
        assert any("余额不符" in w for w in r["warnings"])

    def test_期初不平衡给出警告(self):
        rows = [[1, "1001", "库存现金", "2022-04-01", "期初余额", "", 100.00, None, "借", 100.00]]
        st, r = upload(p("/api/data/import/detail-ledger"), "open.xlsx", xlsx(rows))
        assert st == 200
        assert r["opening_balanced"] is False
        assert any("期初试算不平衡" in w for w in r["warnings"])

    def test_期初行缺年份报错(self):
        # 期初年份未设置且日期为空的期初行无法定年份
        put(p("/api/settings"), {"opening_year": ""})
        rows = [[1, "1001", "库存现金", "", "期初余额", "", 1.00, None, "借", 1.00]]
        st, r = upload(p("/api/data/import/detail-ledger"), "noyear.xlsx", xlsx(rows))
        assert st == 400
        assert "无法确定年份" in r["detail"]

    def test_期初年份参数可指定(self):
        rows = [[1, "1001", "库存现金", "", "期初余额", "", 1.00, None, "借", 1.00]]
        st, r = upload(p("/api/data/import/detail-ledger?opening_year=2035"),
                       "noyear.xlsx", xlsx(rows))
        assert st == 200
        assert r["opening_years"] == ["2035"]

    def test_空文件报错(self):
        st, r = upload(p("/api/data/import/detail-ledger"), "empty.xlsx", b"not-a-spreadsheet")
        assert st == 400

    def test_csv格式可导入(self):
        csv_text = "\n".join([
            ",".join(HEADERS),
            "1,1001,库存现金,2022-05-01,记-501,提现,200.00,,借,200.00",
            "2,1002,银行存款,2022-05-01,记-501,提现,,200.00,贷,200.00",
        ])
        st, r = upload(p("/api/data/import/detail-ledger"), "a.csv", csv_text.encode("utf-8"))
        assert st == 200
        assert r["created_vouchers"] == 1

    def test_表头乱序可识别(self):
        headers = ["摘要", "贷方", "科目", "凭证号", "余额", "借方", "日期", "科目编码", "方向", "序号"]
        rows = [["提现", 200.00, "银行存款", "记-502", 200.00, None, "2022-05-02", "1002", "贷", 1],
                ["提现", None, "库存现金", "记-502", 200.00, 200.00, "2022-05-02", "1001", "借", 2]]
        st, r = upload(p("/api/data/import/detail-ledger"), "shuffle.xlsx", xlsx(rows, headers))
        assert st == 200
        assert r["created_vouchers"] == 1
        assert r["errors"] == []
