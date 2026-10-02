"""多账套（bookset）管理测试：新建/复制/隔离/默认切换/删除/期初年份"""
import pytest

from conftest import api, delete, get, post, put, upload


def _cleanup(*bids):
    for b in bids:
        delete(f"/api/booksets/{b}")


@pytest.fixture(scope="module", autouse=True)
def books(server):
    """准备测试账套并恢复默认账套设置"""
    _cleanup("t07a", "t07b", "t07c", "t07d")
    default = get("/api/booksets")[1]
    assert any(b["id"] == "default" and b["is_default"] for b in default)
    yield
    # 恢复默认账套为 default，再清理测试账套
    put("/api/booksets/default", {"is_default": True})
    _cleanup("t07a", "t07b", "t07c", "t07d")


class TestBooksetList:
    def test_列表包含默认账套(self):
        rows = get("/api/booksets")[1]
        d = next(b for b in rows if b["id"] == "default")
        assert d["is_default"] is True
        assert d["account_count"] > 0
        assert d["name"]

    def test_新建账套带期初年份(self):
        st, r = post("/api/booksets", {"id": "t07a", "name": "甲公司", "opening_year": "2021"})
        assert st == 200 and r["id"] == "t07a"
        rows = get("/api/booksets")[1]
        b = next(x for x in rows if x["id"] == "t07a")
        assert b["name"] == "甲公司"
        assert b["is_default"] is False
        assert b["opening_year"] == "2021"
        assert b["account_count"] > 50   # 空账套也带标准科目表

    def test_新建账套期初年份非法被拒(self):
        st, r = post("/api/booksets", {"id": "t07x", "name": "非法", "opening_year": "21"})
        assert st == 400
        assert not any(b["id"] == "t07x" for b in get("/api/booksets")[1])

    def test_账套名称必填(self):
        assert post("/api/booksets", {"name": "  "})[0] == 400

    def test_重复账套id被拒(self):
        assert post("/api/booksets", {"id": "t07a", "name": "重复"})[0] == 400

    def test_账套不存在(self):
        st, r = api("GET", "/api/accounts?book_id=不存在的账套")
        assert st == 400
        st, r = get("/api/booksets/no-such/openings")
        assert st == 404


class TestBooksetIsolation:
    def test_账套数据相互隔离(self):
        # 在 t07a 建科目（带账套参数）
        st, r = post("/api/accounts?book_id=t07a", {"code": "100101", "name": "备用金A"})
        assert st == 200
        codes_a = {a["code"] for a in get("/api/accounts?book_id=t07a")[1]}
        codes_d = {a["code"] for a in get("/api/accounts?book_id=default")[1]}
        assert "100101" in codes_a
        assert "100101" not in codes_d

    def test_期初年份各账套独立(self):
        assert put("/api/accounts/openings/set-year?book_id=t07a", {"year": "2021"})[0] == 200
        assert post("/api/booksets", {"id": "t07b", "name": "乙公司", "opening_year": "2022"})[0] == 200
        assert get("/api/accounts/openings/years?book_id=t07a")[1]["opening_year"] == "2021"
        assert get("/api/accounts/openings/years?book_id=t07b")[1]["opening_year"] == "2022"

    def test_凭证数据隔离(self):
        acc_a = {a["code"]: a["id"] for a in get("/api/accounts?book_id=t07a")[1]}
        st, _ = put("/api/accounts/openings/save?book_id=t07a", {
            "year": "2021", "rows": [{"account_id": acc_a["1002"], "debit": 1000},
                                     {"account_id": acc_a["3001"], "credit": 1000}]})
        assert st == 200
        # t07a 的期初不影响 default（同一年度）
        d_rows = get("/api/accounts/openings/list?year=2021&book_id=default")[1]["rows"]
        a_rows = get("/api/accounts/openings/list?year=2021&book_id=t07a")[1]["rows"]
        assert any(r["debit"] == 1000 for r in a_rows)
        assert not any((r["debit"] or 0) or (r["credit"] or 0) for r in d_rows)

    def test_账套备份相互独立(self):
        info_a = get("/api/data/backup/info?book_id=t07a")[1]
        info_d = get("/api/data/backup/info?book_id=default")[1]
        assert info_a["book_id"] == "t07a" and info_d["book_id"] == "default"
        assert info_a["db_path"] != info_d["db_path"]


class TestBooksetCopyRenameDelete:
    def test_复制账套含数据(self):
        st, r = post("/api/booksets", {"id": "t07c", "name": "甲公司副本", "copy_from": "t07a"})
        assert st == 200
        rows = get("/api/accounts/openings/list?year=2021&book_id=t07c")[1]["rows"]
        assert any(x["debit"] == 1000 for x in rows)   # 期初被复制
        assert get("/api/accounts/openings/years?book_id=t07c")[1]["opening_year"] == "2021"

    def test_复制不存在的账套被拒(self):
        assert post("/api/booksets", {"id": "t07y", "name": "x", "copy_from": "no-such"})[0] == 400

    def test_重命名与备注(self):
        assert put("/api/booksets/t07c", {"name": "丙公司", "remark": "测试备注"})[0] == 200
        b = next(x for x in get("/api/booksets")[1] if x["id"] == "t07c")
        assert b["name"] == "丙公司" and b["remark"] == "测试备注"

    def test_设为默认与还原(self):
        assert put("/api/booksets/t07c", {"is_default": True})[0] == 200
        rows = get("/api/booksets")[1]
        assert next(x for x in rows if x["id"] == "t07c")["is_default"] is True
        # 不带账套参数的请求落到默认账套（t07c 中有 100101 科目）
        assert any(a["code"] == "100101" for a in get("/api/accounts")[1])
        assert put("/api/booksets/default", {"is_default": True})[0] == 200
        assert next(x for x in get("/api/booksets")[1] if x["id"] == "default")["is_default"] is True

    def test_删除账套(self):
        assert delete("/api/booksets/t07c")[0] == 200
        assert not any(x["id"] == "t07c" for x in get("/api/booksets")[1])
        assert api("GET", "/api/accounts?book_id=t07c")[0] == 400

    def test_默认账套不能删除(self):
        assert delete("/api/booksets/default")[0] == 400

    def test_当前默认账套不能删除(self):
        assert put("/api/booksets/t07b", {"is_default": True})[0] == 200
        st, r = delete("/api/booksets/t07b")
        assert st == 400
        assert "默认" in r["detail"]
        put("/api/booksets/default", {"is_default": True})


class TestBooksetOpenings:
    def test_账套期初概况(self):
        r = get("/api/booksets/t07a/openings?year=2021")[1]
        assert r["book_id"] == "t07a"
        assert r["opening_year"] == "2021"
        assert r["total_debit"] == 1000 and r["total_credit"] == 1000
        assert r["count"] >= 1

    def test_账套期初概况默认年份(self):
        r = get("/api/booksets/t07b/openings")[1]
        assert r["year"] == "2022"
