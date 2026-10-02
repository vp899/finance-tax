"""全量结转（18 步）/ 一键结转 / 结转配置 / 年度区间查询 / 期初修改 / 凭证删除作废 测试

会计年度 2033（2034 用于跨年锚定），顺序场景：
  期初：银行存款 200000（借）/ 实收资本 200000（贷）
  2033-01：购货 20000；销售 51500（收入 50000 + 税 1500）；外币应收 7200（USD，汇率 7）
          固定资产 120000（残值5%/120月 → 月折旧 950）；无形资产 60000（/120月 → 月摊销 500）
  2033-02：销售 206000（收入 200000 + 税 6000）；购货 60000
"""
import pytest

from conftest import acc_id, api, delete, get, make_voucher, post, put


@pytest.fixture(scope="module", autouse=True)
def scenario(accounts):
    assert put("/api/accounts/openings/save", {
        "year": "2033",
        "rows": [{"account_id": acc_id("1002", accounts), "debit": 200000},
                 {"account_id": acc_id("3001", accounts), "credit": 200000}]} )[0] == 200
    # 外币明细科目（应收账款-美元户）
    st, r = post("/api/accounts", {
        "code": "112201", "name": "应收账款-美元户", "parent_code": "1122",
        "direction": "D", "category": "asset", "currency": "USD"})
    assert st == 200
    assert make_voucher("2033-01-05", [
        ("1405", "购进商品", 20000, 0), ("2202", "购进商品", 0, 20000)])[0] == 200
    assert make_voucher("2033-01-10", [
        ("1002", "销售商品", 51500, 0), ("5001", "销售商品", 0, 50000),
        ("222101", "销售商品", 0, 1500)])[0] == 200
    # 外币销售：应收 1028.57 USD（7200 / 汇率 7）
    st, r = post("/api/vouchers", {
        "date": "2033-01-15", "entries": [
            {"account_id": acc_id("112201"), "summary": "外币销售",
             "debit": 7200, "credit": 0, "currency": "USD", "exchange_rate": 7},
            {"account_id": acc_id("5001", accounts), "summary": "外币销售",
             "debit": 0, "credit": 7200}]})
    assert st == 200
    # 停用其他测试套件遗留的资产，保证折旧/摊销金额确定
    for f in get("/api/carryover/assets/fixed")[1]:
        assert put(f"/api/carryover/assets/fixed/{f['id']}", {"in_use": False})[0] == 200
    for f in get("/api/carryover/assets/intangible")[1]:
        assert put(f"/api/carryover/assets/intangible/{f['id']}", {"in_use": False})[0] == 200
    assert post("/api/carryover/assets/fixed", {
        "name": "生产设备", "original_value": 120000, "residual_rate": 0.05,
        "life_months": 120, "expense_account_code": "560202"})[0] == 200
    assert post("/api/carryover/assets/intangible", {
        "name": "管理软件", "original_value": 60000, "amort_months": 120,
        "expense_account_code": "560203"})[0] == 200
    yield


def _gl(period):
    return {x["code"]: x for x in get(f"/api/books/general-ledger?period={period}")[1]["rows"]}


def _tb(period=None, **kw):
    q = f"period={period}" if period else "&".join(f"{k}={v}" for k, v in kw.items())
    return get(f"/api/books/trial-balance?{q}")[1]


def _entries(voucher_id):
    return {e["account_code"]: e for e in get(f"/api/vouchers/{voucher_id}")[1]["entries"]}


class TestCarryoverConfig:
    def test_步骤清单包含全部十八步(self):
        rows = get("/api/carryover/kinds")[1]
        names = [r["name"] for r in rows]
        for n in ["结转销售成本", "计提工资", "发放工资", "发放全年一次性奖金", "计提折旧",
                  "摊销无形资产", "摊销待摊费用", "免交增值税", "计提全年一次性奖金",
                  "计提劳务报酬", "发放劳务报酬", "计提税金", "地方水利基金", "印花税",
                  "工会经费", "计提所得税", "结转汇兑损益", "结转本期损益", "结转未分配利润"]:
            assert n in names, n
        orders = [r["order"] for r in rows]
        assert orders == sorted(orders)

    def test_配置可保存与回读(self):
        st, cfg = put("/api/carryover/config", {
            "rates": {"water_fund": 0.01},
            "steps": {"sales_cost": {"default_amount": 12345}}})
        assert st == 200
        assert cfg["rates"]["water_fund"] == 0.01
        st, cfg2 = get("/api/carryover/config")
        assert cfg2["rates"]["water_fund"] == 0.01
        assert cfg2["steps"]["sales_cost"]["default_amount"] == 12345

    def test_非法配置被拒(self):
        assert put("/api/carryover/config", {"steps": {"unknown": {}}})[0] == 400
        assert put("/api/carryover/config", {"rates": {"bad_rate": 0.1}})[0] == 400
        assert put("/api/carryover/config", {"rates": {"city": 5}})[0] == 400

    def test_配置恢复默认费率(self):
        assert put("/api/carryover/config", {
            "rates": {"water_fund": 0.005},
            "steps": {"sales_cost": {"default_amount": 0}}})[0] == 200


class TestNewCarryoverKinds:
    """2033-01 逐项执行新结转"""

    def test_计提全年一次性奖金(self):
        st, r = post("/api/carryover/accrue_bonus", {"period": "2033-01", "amount": 8000})
        assert st == 200 and r["amount"] == 8000
        es = _entries(r["voucher_id"])
        assert es["560201"]["debit"] == 8000
        assert es["221101"]["credit"] == 8000

    def test_发放工资带代扣个税(self):
        st, r = post("/api/carryover/pay_salary", {
            "period": "2033-01", "amount": 8000, "withheld": 240})
        assert st == 200 and r["amount"] == 8000
        es = _entries(r["voucher_id"])
        assert es["221101"]["debit"] == 8000
        assert es["1002"]["credit"] == 7760
        assert es["222113"]["credit"] == 240

    def test_发放工资金额不能超过应发(self):
        st, _ = post("/api/carryover/pay_salary", {
            "period": "2033-01", "amount": 100, "withheld": 100})
        assert st == 400

    def test_计提劳务报酬(self):
        st, r = post("/api/carryover/accrue_labor", {"period": "2033-01", "amount": 3000})
        assert st == 200 and r["amount"] == 3000
        es = _entries(r["voucher_id"])
        assert es["560212"]["debit"] == 3000
        assert es["224101"]["credit"] == 3000

    def test_发放劳务报酬(self):
        st, r = post("/api/carryover/pay_labor", {
            "period": "2033-01", "amount": 3000, "withheld": 480})
        assert st == 200
        es = _entries(r["voucher_id"])
        assert es["224101"]["debit"] == 3000
        assert es["1002"]["credit"] == 2520
        assert es["222113"]["credit"] == 480

    def test_摊销待摊费用(self):
        st, r = post("/api/carryover/amortize_deferred", {"period": "2033-01", "amount": 600})
        assert st == 200 and r["amount"] == 600
        es = _entries(r["voucher_id"])
        assert es["560203"]["debit"] == 600
        assert es["1801"]["credit"] == 600

    def test_计提折旧与摊销(self):
        st, r = post("/api/carryover/depreciation", {"period": "2033-01"})
        assert st == 200 and r["amount"] == 950
        st, r = post("/api/carryover/amortization", {"period": "2033-01"})
        assert st == 200 and r["amount"] == 500

    def test_免交增值税自动使用末级科目(self):
        st, r = post("/api/carryover/vat_free", {"period": "2033-01"})
        assert st == 200 and r["amount"] == 1500
        es = _entries(r["voucher_id"])
        assert es["222101"]["debit"] == 1500
        # 营业外收入下自动生成末级明细
        assert es["530102"]["credit"] == 1500
        gl = _gl("2033-01")
        assert gl["5301"]["closing_credit"] == 1500

    def test_地方水利基金(self):
        st, r = post("/api/carryover/water_fund", {"period": "2033-01"})
        # 本期营业收入 57200 × 0.5% = 286
        assert st == 200 and r["amount"] == 286
        es = _entries(r["voucher_id"])
        assert es["540310"]["debit"] == 286
        assert es["222115"]["credit"] == 286

    def test_印花税(self):
        st, r = post("/api/carryover/stamp_tax", {"period": "2033-01", "amount": 30})
        assert st == 200 and r["amount"] == 30
        es = _entries(r["voucher_id"])
        assert es["540304"]["debit"] == 30
        assert es["222114"]["credit"] == 30

    def test_工会经费按工资基数(self):
        st, r = post("/api/carryover/union_fee", {"period": "2033-01"})
        # 本期工资计提 8000 × 2% = 160
        assert st == 200 and r["amount"] == 160
        es = _entries(r["voucher_id"])
        assert es["560213"]["debit"] == 160
        assert es["221104"]["credit"] == 160

    def test_结转汇兑损益(self):
        st, r = post("/api/carryover/exchange", {"period": "2033-01"})
        # 原币 7200/7 = 1028.57 USD × 7.2 = 7405.70 − 账面 7200 = 205.70
        assert st == 200 and r["amount"] == 205.7
        es = _entries(r["voucher_id"])
        assert es["112201"]["debit"] == 205.7
        assert es["560304"]["credit"] == 205.7

    def test_汇兑损益幂等(self):
        st, r = post("/api/carryover/exchange", {"period": "2033-01"})
        assert st == 400  # 已调整，无差额

    def test_税金计提免税后基数为零(self):
        st, r = post("/api/carryover/tax", {"period": "2033-01"})
        assert st == 400  # 免交增值税后应交增值税为 0

    def test_结转本期损益(self):
        st, r = post("/api/carryover/profit", {"period": "2033-01"})
        assert st == 200, r

    def test_一月试算与报表平衡(self):
        assert _tb("2033-01")["balanced"] is True
        bs = get("/api/reports/balance-sheet?period=2033-01")[1]
        assert bs["balanced"] is True


class TestTaxIncomeTaxRetain:
    """2033-02：税金、所得税、损益结转、未分配利润"""

    def test_二月业务凭证(self):
        assert make_voucher("2033-02-05", [
            ("1405", "购进商品", 60000, 0), ("2202", "购进商品", 0, 60000)])[0] == 200
        assert make_voucher("2033-02-10", [
            ("1002", "销售商品", 206000, 0), ("5001", "销售商品", 0, 200000),
            ("222101", "销售商品", 0, 6000)])[0] == 200

    def test_免交增值税不达条件被拒(self):
        st, _ = post("/api/carryover/vat_free", {"period": "2033-02"})
        assert st == 400

    def test_计提税金(self):
        st, r = post("/api/carryover/tax", {"period": "2033-02"})
        # 基数 6000 → 城建 420 + 教育 180 + 地方教育 120 = 720
        assert st == 200 and r["amount"] == 720
        es = _entries(r["voucher_id"])
        assert es["540301"]["debit"] == 420 and es["222106"]["credit"] == 420

    def test_计提所得税(self):
        pv = get("/api/carryover/preview/income-tax?period=2033-02")[1]
        st, r = post("/api/carryover/income_tax", {"period": "2033-02"})
        assert st == 200 and r["amount"] == pv["amount"] and r["amount"] > 0
        es = _entries(r["voucher_id"])
        assert es["5801"]["debit"] == r["amount"]
        assert es["222112"]["credit"] == r["amount"]

    def test_结转本期损益(self):
        st, r = post("/api/carryover/profit", {"period": "2033-02"})
        assert st == 200

    def test_结转未分配利润(self):
        gl = _gl("2033-02")
        bal = gl["3103"]["closing_credit"] - gl["3103"]["closing_debit"]
        assert bal > 0  # 盈利
        st, r = post("/api/carryover/retain_profit", {"period": "2033-02"})
        assert st == 200 and r["amount"] == bal
        es = _entries(r["voucher_id"])
        assert es["3103"]["debit"] == bal
        assert es["3104"]["credit"] == bal
        gl = _gl("2033-02")
        assert gl["3103"]["closing_debit"] == 0 and gl["3103"]["closing_credit"] == 0

    def test_结转后试算与结账(self):
        assert _tb("2033-02")["balanced"] is True
        st, r = post("/api/carryover/close", {"period": "2033-02"})
        assert st == 200 and r["status"] == "closed"
        assert post("/api/carryover/open", {"period": "2033-02"})[0] == 200


class TestOneClick:
    def test_一键结转按顺序执行(self):
        st, r = post("/api/carryover/run-all", {
            "period": "2033-03",
            "amounts": {"sales_cost": 10000, "salary": 5000}})
        assert st == 200
        res = {x["kind"]: x for x in r["results"]}
        assert res["sales_cost"]["status"] == "created"
        assert res["sales_cost"]["amount"] == 10000
        assert res["salary"]["amount"] == 5000
        assert res["depreciation"]["amount"] == 950
        assert res["exchange"]["status"] == "skipped"  # 汇兑损益已调整，幂等跳过
        assert r["created_count"] >= 6
        assert _tb("2033-03")["balanced"] is True

    def test_一键结转结果含凭证号(self):
        rows = get("/api/carryover/records?period=2033-03")[1]
        assert any(x["kind"] == "sales_cost" and x["voucher_no"] for x in rows)

    def test_停用步骤被跳过(self):
        cfg = get("/api/carryover/config")[1]
        cfg["steps"]["sales_cost"]["enabled"] = False
        assert put("/api/carryover/config", cfg)[0] == 200
        st, r = post("/api/carryover/run-all", {"period": "2033-04"})
        assert st == 200
        res = {x["kind"]: x for x in r["results"]}
        assert res["sales_cost"]["status"] == "disabled"
        cfg["steps"]["sales_cost"]["enabled"] = True
        assert put("/api/carryover/config", cfg)[0] == 200

    def test_默认金额用于一键结转(self):
        cfg = get("/api/carryover/config")[1]
        cfg["steps"]["sales_cost"]["default_amount"] = 3333
        assert put("/api/carryover/config", cfg)[0] == 200
        st, r = post("/api/carryover/run-all", {
            "period": "2033-04", "kinds": ["sales_cost"]})
        assert st == 200
        assert r["results"][0]["amount"] == 3333
        cfg["steps"]["sales_cost"]["default_amount"] = 0
        assert put("/api/carryover/config", cfg)[0] == 200

    def test_结账期间拒绝一键结转(self):
        assert post("/api/carryover/close", {"period": "2033-04", "force": True})[0] == 200
        st, _ = post("/api/carryover/run-all", {"period": "2033-04"})
        assert st == 400
        assert post("/api/carryover/open", {"period": "2033-04"})[0] == 200


class TestYearRangeQuery:
    def test_凭证按年度查询(self):
        st, r = get("/api/vouchers?year=2033&size=100")
        assert st == 200 and r["total"] > 5
        assert all(x["period"].startswith("2033") for x in r["rows"])

    def test_凭证按区间查询(self):
        st, r = get("/api/vouchers?from_period=2033-01&to_period=2033-01&size=100")
        assert st == 200 and r["total"] > 0
        assert all(x["period"] == "2033-01" for x in r["rows"])

    def test_试算平衡按年度与区间(self):
        assert _tb(year="2033")["balanced"] is True
        r = get("/api/books/trial-balance?from_period=2033-01&to_period=2033-03")[1]
        assert r["balanced"] is True
        assert r["from_period"] == "2033-01" and r["to_period"] == "2033-03"

    def test_总账年度与区间期末一致(self):
        yr = get("/api/books/general-ledger?year=2033")[1]["rows"]
        rg = get("/api/books/general-ledger?from_period=2033-01&to_period=2033-12")[1]["rows"]
        assert yr == rg
        m = {x["code"]: x for x in yr}
        assert m["1002"]["closing_debit"] == _gl("2033-12")["1002"]["closing_debit"]

    def test_利润表年度区间(self):
        r = get("/api/reports/income?year=2033")[1]
        assert r["mode"] == "range"
        rows = {x["name"]: x for x in r["rows"]}
        assert rows["一、营业收入"]["current"] == 257200  # 50000 + 7200 + 200000
        r2 = get("/api/reports/income?from_period=2033-02&to_period=2033-02")[1]
        rows2 = {x["name"]: x for x in r2["rows"]}
        assert rows2["一、营业收入"]["current"] == 200000

    def test_现金流量表年度(self):
        r = get("/api/reports/cashflow?year=2033")[1]
        assert r["from_period"] == "2033-01" and r["to_period"] == "2033-12"
        assert r["rows"]

    def test_结转记录按年度与区间(self):
        st, r = get("/api/carryover/records?year=2033")
        assert st == 200 and len(r) > 5
        assert all(x["period"].startswith("2033") for x in r)
        st, r2 = get("/api/carryover/records?from_period=2033-01&to_period=2033-01")
        assert st == 200 and all(x["period"] == "2033-01" for x in r2)


class TestOpeningEdit:
    def test_修改期初成功(self):
        st, r = put("/api/accounts/openings/save", {
            "year": "2033",
            "rows": [{"account_id": acc_id("1002"), "debit": 250000},
                     {"account_id": acc_id("3001"), "credit": 250000}]})
        assert st == 200
        rows = {x["code"]: x for x in get("/api/accounts/openings/list?year=2033")[1]["rows"]}
        assert rows["1002"]["debit"] == 250000
        assert _tb("2033-01")["balanced"] is True

    def test_单边修改被拒(self):
        st, r = put("/api/accounts/openings/save", {
            "year": "2033",
            "rows": [{"account_id": acc_id("1002"), "debit": 999}]})
        assert st == 400 and "不平衡" in r["detail"]

    def test_重复科目行被拒(self):
        st, r = put("/api/accounts/openings/save", {
            "year": "2033",
            "rows": [{"account_id": acc_id("1002"), "debit": 100},
                     {"account_id": acc_id("1002"), "debit": 50},
                     {"account_id": acc_id("3001"), "credit": 150}]})
        assert st == 400 and "重复" in r["detail"]

    def test_负数期初被拒(self):
        st, _ = put("/api/accounts/openings/save", {
            "year": "2033",
            "rows": [{"account_id": acc_id("1002"), "debit": -1},
                     {"account_id": acc_id("3001"), "credit": -1}]})
        assert st == 400

    def test_修改后恢复原值(self):
        assert put("/api/accounts/openings/save", {
            "year": "2033",
            "rows": [{"account_id": acc_id("1002"), "debit": 200000},
                     {"account_id": acc_id("3001"), "credit": 200000}]})[0] == 200


class TestVoucherDeleteVoid:
    def test_作废与恢复凭证(self):
        st, v = make_voucher("2033-05-10", [
            ("560204", "作废测试", 10, 0), ("1002", "作废测试", 0, 10)])
        assert st == 200
        st, r = post(f"/api/vouchers/{v['id']}/void")
        assert st == 200 and r["status"] == "voided"
        st, r = post(f"/api/vouchers/{v['id']}/void")
        assert st == 200 and r["status"] == "posted"

    def test_作废结转凭证同步结转记录(self):
        st, r = post("/api/carryover/salary", {"period": "2033-05", "amount": 1000})
        assert st == 200
        rec = next(x for x in get("/api/carryover/records?period=2033-05")[1]
                   if x["kind"] == "salary")
        assert rec["status"] == "active"
        st, _ = post(f"/api/vouchers/{r['voucher_id']}/void")
        assert st == 200
        rec = next(x for x in get("/api/carryover/records?period=2033-05")[1]
                   if x["kind"] == "salary")
        assert rec["status"] == "reversed"
        assert _tb("2033-05")["balanced"] is True

    def test_删除凭证(self):
        st, v = make_voucher("2033-05-11", [
            ("560204", "删除测试", 20, 0), ("1002", "删除测试", 0, 20)])
        assert st == 200
        st, r = delete(f"/api/vouchers/{v['id']}")
        assert st == 200 and r["ok"] is True
        assert get(f"/api/vouchers/{v['id']}")[0] == 404
        assert _tb("2033-05")["balanced"] is True

    def test_删除结转凭证同时删除结转记录(self):
        st, r = post("/api/carryover/salary", {"period": "2033-05", "amount": 2000})
        assert st == 200
        before = len(get("/api/carryover/records?period=2033-05")[1])
        st, dr = delete(f"/api/vouchers/{r['voucher_id']}")
        assert st == 200 and dr["carryover_records_removed"] == 1
        assert len(get("/api/carryover/records?period=2033-05")[1]) == before - 1

    def test_结账后删除被拒(self):
        assert post("/api/carryover/close", {"period": "2033-05", "force": True})[0] == 200
        vid = get("/api/vouchers?period=2033-05")[1]["rows"][0]["id"]
        assert delete(f"/api/vouchers/{vid}")[0] == 400
        assert post("/api/carryover/open", {"period": "2033-05"})[0] == 200


class TestTrialBalanceRobust:
    def test_下级科目新增后试算仍平衡(self):
        assert _tb("2033-05")["balanced"] is True
        st, r = post("/api/accounts", {
            "code": "100201", "name": "工行存款", "parent_code": "1002",
            "direction": "D", "category": "asset"})
        assert st == 200
        tb = _tb("2033-05")
        assert tb["balanced"] is True
        # 原 1002 的发生额仍计入试算（非末级直接记账兜底）
        rows = {x["code"]: x for x in tb["rows"]}
        assert rows["1002"]["is_leaf"] is False
        assert rows["1002"]["closing_debit"] == _gl("2033-05")["1002"]["closing_debit"] > 0
        # 清理：删除新增下级
        assert delete(f"/api/accounts/{r['id']}")[0] == 200

    def test_有期初的科目不能删除(self):
        st, r = post("/api/accounts", {
            "code": "112202", "name": "测试应收", "parent_code": "1122",
            "direction": "D", "category": "asset"})
        assert st == 200
        assert put("/api/accounts/openings/save", {
            "year": "2035",
            "rows": [{"account_id": r["id"], "debit": 500},
                     {"account_id": acc_id("3001"), "credit": 500}]})[0] == 200
        st, msg = delete(f"/api/accounts/{r['id']}")
        assert st == 400 and "期初" in msg["detail"]
        # 清理：清零期初后可删除
        assert put("/api/accounts/openings/save", {
            "year": "2035",
            "rows": [{"account_id": r["id"], "debit": 0},
                     {"account_id": acc_id("3001"), "credit": 0}]})[0] == 200
        assert delete(f"/api/accounts/{r['id']}")[0] == 200

    def test_期初不平衡不能保存(self):
        st, _ = put("/api/accounts/openings/save", {
            "year": "2036",
            "rows": [{"account_id": acc_id("1002"), "debit": 100}]})
        assert st == 400
        rows = get("/api/accounts/openings/list?year=2036")[1]
        assert rows["total_debit"] == 0


class TestCrossYearAnchor:
    def test_新年度未录入期初时余额连续(self):
        assert make_voucher("2034-01-06", [
            ("1002", "跨年收款", 100, 0), ("5001", "跨年收款", 0, 100)])[0] == 200
        dec = _gl("2033-12")["1002"]["closing_debit"]
        jan = _gl("2034-01")["1002"]
        assert jan["closing_debit"] == dec + 100  # 锚定期初连续，不被清零
        assert _tb("2034-01")["balanced"] is True

    def test_跨年区间查询期末一致(self):
        yr = {x["code"]: x for x in
              get("/api/books/general-ledger?from_period=2033-01&to_period=2034-01")[1]["rows"]}
        assert yr["1002"]["closing_debit"] == _gl("2034-01")["1002"]["closing_debit"]
        r = get("/api/books/trial-balance?from_period=2033-01&to_period=2034-01")[1]
        assert r["balanced"] is True
