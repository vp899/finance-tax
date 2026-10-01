"""科目管理 + 期初余额 测试（会计年度 2026）"""
import pytest

from conftest import acc_id, api, delete, get, make_voucher, post, put


@pytest.fixture(scope="module", autouse=True)
def _need_server(accounts):
    pass


class TestAccounts:
    def test_科目表已初始化(self, accounts):
        assert len(accounts) >= 80

    def test_内置科目含关键科目(self, accounts):
        codes = {a["code"] for a in accounts}
        for c in ["1001", "1002", "1405", "1601", "2221", "222101", "3103", "5001", "5602"]:
            assert c in codes

    def test_末级与非末级标记(self, accounts):
        by_code = {a["code"]: a for a in accounts}
        assert by_code["5602"]["is_leaf"] is False
        assert by_code["560201"]["is_leaf"] is True

    def test_按编码前缀补全(self):
        st, r = get("/api/accounts/suggest?q=5602")
        assert st == 200
        assert any(a["code"] == "5602" for a in r)

    def test_按拼音首字母补全(self):
        st, r = get("/api/accounts/suggest?q=yhck")
        assert st == 200
        assert any(a["code"] == "1002" for a in r)

    def test_按名称补全(self):
        st, r = get("/api/accounts/suggest?q=银行存款")
        assert st == 200
        assert any(a["code"] == "1002" for a in r)

    def test_补全返回余额与末级标记(self):
        st, r = get("/api/accounts/suggest?q=1002")
        assert st == 200
        item = next(a for a in r if a["code"] == "1002")
        assert "balance" in item and item["is_leaf"] is True

    def test_新增下级科目(self, accounts):
        st, r = post("/api/accounts", {
            "code": "560299", "name": "测试费用", "parent_code": "5602",
            "direction": "D", "category": "expense", "pinyin": "csfy",
        })
        assert st == 200 and r["id"]

    def test_新增科目缺名称被拒(self):
        st, r = post("/api/accounts", {"code": "560298"})
        assert st == 400

    def test_重复编码被拒(self):
        st, r = post("/api/accounts", {"code": "1002", "name": "重复科目"})
        assert st == 400

    def test_上级科目不存在被拒(self):
        st, r = post("/api/accounts", {"code": "999901", "name": "测试", "parent_code": "9999"})
        assert st == 400

    def test_更新科目信息(self):
        aid = acc_id("560299")
        st, r = put(f"/api/accounts/{aid}", {"name": "测试费用-改", "pinyin": "csfyg"})
        assert st == 200
        rows = get("/api/accounts")[1]
        assert next(a for a in rows if a["code"] == "560299")["name"] == "测试费用-改"

    def test_有分录的科目不能删除(self):
        st, r = post("/api/accounts", {
            "code": "560297", "name": "被占用科目", "parent_code": "5602",
            "direction": "D", "category": "expense"})
        assert st == 200
        st, v = make_voucher("2026-05-10", [
            ("560297", "占用测试", 100, 0),
            ("1002", "占用测试", 0, 100)])
        assert st == 200
        st, r = delete(f"/api/accounts/{acc_id('560297')}")
        assert st == 400

    def test_有下级的科目不能删除(self):
        st, r = post("/api/accounts", {
            "code": "571199", "name": "父科目测试", "direction": "D", "category": "expense"})
        assert st == 200
        st, r = post("/api/accounts", {
            "code": "57119901", "name": "子科目测试", "parent_code": "571199",
            "direction": "D", "category": "expense"})
        assert st == 200
        st, r = delete(f"/api/accounts/{acc_id('571199')}")
        assert st == 400

    def test_删除无引用科目成功(self):
        st, _ = post("/api/accounts", {
            "code": "560296", "name": "可删科目", "parent_code": "5602",
            "direction": "D", "category": "expense"})
        assert st == 200
        st, r = delete(f"/api/accounts/{acc_id('560296')}")
        assert st == 200
        codes = {a["code"] for a in get("/api/accounts")[1]}
        assert "560296" not in codes


class TestOpeningBalance:
    def test_期初借贷不平衡被拒(self, accounts):
        st, r = put("/api/accounts/openings/save", {
            "year": "2026",
            "rows": [{"account_id": acc_id("1002", accounts), "debit": 1000}]})
        assert st == 400

    def test_期初同一科目借贷同时有值被拒(self, accounts):
        st, r = put("/api/accounts/openings/save", {
            "year": "2026",
            "rows": [{"account_id": acc_id("1002", accounts), "debit": 100, "credit": 50},
                     {"account_id": acc_id("3001", accounts), "credit": 100}]})
        assert st == 400

    def test_非末级科目期初被拒(self, accounts):
        st, r = put("/api/accounts/openings/save", {
            "year": "2026",
            "rows": [{"account_id": acc_id("5602", accounts), "debit": 100},
                     {"account_id": acc_id("3001", accounts), "credit": 100}]})
        assert st == 400

    def test_平衡期初保存成功(self, accounts):
        st, r = put("/api/accounts/openings/save", {
            "year": "2026",
            "rows": [{"account_id": acc_id("1002", accounts), "debit": 500000},
                     {"account_id": acc_id("3001", accounts), "credit": 500000}]})
        assert st == 200 and r["ok"] is True

    def test_期初列表合计正确(self):
        st, r = get("/api/accounts/openings/list?year=2026")
        assert st == 200
        assert r["total_debit"] == 500000 and r["total_credit"] == 500000
        assert r["balanced"] is True

    def test_重跑保存覆盖旧值(self, accounts):
        st, _ = put("/api/accounts/openings/save", {
            "year": "2026",
            "rows": [{"account_id": acc_id("1002", accounts), "debit": 500000},
                     {"account_id": acc_id("3001", accounts), "credit": 500000}]})
        assert st == 200
        r = get("/api/accounts/openings/list?year=2026")[1]
        assert r["total_debit"] == 500000
