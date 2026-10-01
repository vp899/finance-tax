#!/usr/bin/env python3
"""端到端正确性测试：凭证/账簿/报表/结转/反结转/结账/导入导出/备份"""
import io
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"

# 重置服务与数据库，保证测试可重复
import os
import subprocess
subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "restart.sh"), "fresh"], check=True,
               stdout=subprocess.DEVNULL)

PASS, FAIL = 0, 0
failures = []


def api(method, path, body=None, raw=False):
    from urllib.parse import quote
    url = BASE + quote(path, safe="/?&=:%")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload))
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"detail": payload.decode(errors="replace")}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        failures.append(f"{name} {detail}")
        print(f"  ❌ {name}  {detail}")


def eq(name, got, want):
    check(name, got == want, f"got={got!r} want={want!r}")


def close(a, b, eps=0.01):
    return abs(a - b) < eps


print("== 1. 健康检查与科目 ==")
st, h = api("GET", "/api/health")
eq("health", (st, h.get("status")), (200, "ok"))
st, accounts = api("GET", "/api/accounts")
check("科目已初始化", st == 200 and len(accounts) > 50, f"count={len(accounts) if st==200 else st}")
acc_id = {a["code"]: a["id"] for a in accounts}

print("== 2. 期初余额 ==")
st, r = api("PUT", "/api/accounts/openings/save", {
    "year": "2026",
    "rows": [
        {"account_id": acc_id["1002"], "debit": 500000},
        {"account_id": acc_id["3001"], "credit": 500000},
    ]})
eq("期初试算平衡", (st, r.get("ok")), (200, True))
st, r = api("GET", "/api/accounts/openings/list?year=2026")
eq("期初借贷合计", (r["total_debit"], r["total_credit"], r["balanced"]),
   (500000.0, 500000.0, True))

print("== 3. 凭证：合法性校验 ==")
st, r = api("POST", "/api/vouchers", {
    "date": "2026-09-05", "entries": [
        {"account_id": acc_id["1002"], "summary": "不平测试", "debit": 100},
    ]})
check("借贷不平衡被拒绝", st == 400, f"st={st}")
st, r = api("POST", "/api/vouchers", {
    "date": "2026-09-05", "entries": [
        {"account_id": acc_id["5602"], "summary": "非末级", "debit": 100},
        {"account_id": acc_id["1002"], "summary": "非末级", "credit": 100},
    ]})
check("非末级科目被拒绝", st == 400, f"st={st} {r}")

print("== 4. 业务凭证 ==")
vouchers = [
    ("2026-09-03", "购进商品", [("1405", "购进商品", 50000, 0), ("2202", "购进商品", 0, 50000)]),
    ("2026-09-10", "销售商品", [("1002", "销售商品", 103000, 0), ("5001", "销售商品", 0, 100000),
                                ("222101", "销售商品", 0, 3000)]),
    ("2026-09-12", "购置固定资产", [("1601", "购置设备", 120000, 0), ("1002", "购置设备", 0, 120000)]),
    ("2026-09-12", "购置无形资产", [("1701", "购置软件", 60000, 0), ("1002", "购置软件", 0, 60000)]),
    ("2026-09-20", "支付办公费", [("560204", "支付办公费", 2000, 0), ("1002", "支付办公费", 0, 2000)]),
]
for date, summary, lines in vouchers:
    entries = [{"account_id": acc_id[c], "summary": s, "debit": d, "credit": cr}
               for c, s, d, cr in lines]
    st, r = api("POST", "/api/vouchers", {"date": date, "entries": entries})
    check(f"凭证 {summary}", st == 200 and r.get("total_debit") == sum(l[2] for l in lines),
          f"st={st} {r if st != 200 else ''}")

print("== 5. 智能补全 ==")
st, r = api("GET", "/api/vouchers/suggest?q=yhck")
check("拼音首字母补全银行存款", st == 200 and any(a["code"] == "1002" for a in r["accounts"]),
      str(r)[:200])
st, r = api("GET", "/api/vouchers/suggest?q=销售")
check("摘要补全", st == 200 and any("销售" in s for s in r["summaries"]), str(r)[:200])

print("== 6. 固定资产/无形资产 + 结转 ==")
st, r = api("POST", "/api/carryover/assets/fixed", {
    "name": "生产设备", "original_value": 120000, "residual_rate": 0.05,
    "life_months": 120, "expense_account_code": "560202"})
eq("固定资产录入", st, 200)
st, r = api("POST", "/api/carryover/assets/intangible", {
    "name": "管理软件", "original_value": 60000, "amort_months": 120,
    "expense_account_code": "560203"})
eq("无形资产录入", st, 200)

st, r = api("GET", "/api/carryover/preview/depreciation?period=2026-09")
eq("折旧预览 950", (st, r.get("total")), (200, 950.0))
st, r = api("POST", "/api/carryover/depreciation", {"period": "2026-09"})
eq("计提折旧", (st, r.get("amount")), (200, 950.0))

st, r = api("GET", "/api/carryover/preview/amortization?period=2026-09")
eq("摊销预览 500", (st, r.get("total")), (200, 500.0))
st, r = api("POST", "/api/carryover/amortization", {"period": "2026-09"})
eq("摊销无形资产", (st, r.get("amount")), (200, 500.0))

st, r = api("POST", "/api/carryover/sales_cost",
            {"period": "2026-09", "amount": 50000})
eq("结转销售成本", (st, r.get("amount")), (200, 50000.0))

st, r = api("POST", "/api/carryover/salary", {"period": "2026-09", "amount": 20000})
eq("计提工资", (st, r.get("amount")), (200, 20000.0))

st, r = api("GET", "/api/carryover/preview/tax?period=2026-09")
eq("计税基数 3000", (st, r.get("vat_base")), (200, 3000.0))
eq("城建税 210", r.get("city_tax"), 210.0)
st, r = api("POST", "/api/carryover/tax", {"period": "2026-09"})
check("计提税金成功", st == 200, f"st={st} {r}")

st, r = api("GET", "/api/carryover/preview/income-tax?period=2026-09")
eq("累计利润总额 26190", r.get("total_profit_ytd"), 26190.0)  # 100000-50000-360-20000-950-500-2000
eq("所得税 6547.5", r.get("amount"), 6547.5)
st, r = api("POST", "/api/carryover/income_tax", {"period": "2026-09"})
eq("计提所得税", (st, r.get("amount")), (200, 6547.5))

st, r = api("POST", "/api/carryover/profit", {"period": "2026-09"})
check("结转本期损益", st == 200 and r.get("amount") > 0, f"st={st} {r}")

print("== 7. 账簿 ==")
st, gl = api("GET", "/api/books/general-ledger?period=2026-09")
row1002 = next(r for r in gl["rows"] if r["code"] == "1002")
eq("总账 1002 本期借方", row1002["period_debit"], 103000.0)
eq("总账 1002 期末借方", row1002["closing_debit"], 421000.0)
row5602 = next(r for r in gl["rows"] if r["code"] == "5602")
eq("总账 5602 汇总下级 本期借方", row5602["period_debit"], 23450.0)  # 20000+950+500+2000

st, det = api("GET", "/api/books/detail?account_code=1002&from_period=2026-09&to_period=2026-09")
check("明细账 1002 有流水", st == 200 and len(det["rows"]) == 4, f"rows={len(det.get('rows', []))}")
eq("明细账期初 500000", det["opening"]["debit"], 500000.0)

st, jr = api("GET", "/api/books/journal?from_period=2026-09&to_period=2026-09")
eq("序时账借贷合计相等", (st, jr["total_debit"] == jr["total_credit"]), (200, True))
check("序时账有分录", len(jr["rows"]) > 15, f"rows={len(jr['rows'])}")

st, bt = api("GET", "/api/books/balance-table?period=2026-09")
check("余额表", st == 200 and len(bt["rows"]) > 50)

st, mc = api("GET", "/api/books/multi-column?account_code=5602&from_period=2026-09&to_period=2026-09")
check("多栏账按明细展开", st == 200 and len(mc["columns"]) >= 4, str(mc.get("columns")))

st, tb = api("GET", "/api/books/trial-balance?period=2026-09")
eq("试算平衡", (st, tb["balanced"]), (200, True))
check("试算合计一致", close(tb["total_debit"], tb["total_credit"]),
      f"{tb['total_debit']} vs {tb['total_credit']}")

print("== 8. 报表 ==")
st, bs = api("GET", "/api/reports/balance-sheet?period=2026-09")
eq("资产负债表平衡", (st, bs["balanced"]), (200, True))
bmap = {r["name"]: r for r in bs["rows"]}
eq("货币资金 421000", bmap["货币资金"]["ending"], 421000.0)
eq("存货 0", bmap["存货"]["ending"], 0.0)
eq("固定资产净额 119050", bmap["固定资产净额"]["ending"], 119050.0)
eq("无形资产 59500", bmap["无形资产"]["ending"], 59500.0)
eq("资产总计 599550", bmap["资产总计"]["ending"], 599550.0)
eq("负债合计 79907.5", bmap["负债合计"]["ending"], 79907.5)
eq("未分配利润 19642.5", bmap["未分配利润"]["ending"], 19642.5)

st, inc = api("GET", "/api/reports/income?period=2026-09&mode=month")
imap = {r["name"]: r for r in inc["rows"]}
eq("利润表 营业收入 100000", imap["一、营业收入"]["ytd"], 100000.0)
eq("利润表 营业成本 50000", imap["　减：营业成本"]["ytd"], 50000.0)
eq("利润表 管理费用 23450", imap["　　　管理费用"]["ytd"], 23450.0)
eq("利润表 利润总额 26190", imap["三、利润总额（亏损以“-”号填列）"]["ytd"], 26190.0)
eq("利润表 净利润 19642.5", imap["四、净利润（净亏损以“-”号填列）"]["ytd"], 19642.5)

st, incq = api("GET", "/api/reports/income?period=2026-09&mode=quarter")
eq("利润表季报本季金额", incq["rows"][0]["quarter"], 100000.0)

st, cf = api("GET", "/api/reports/cashflow?from_period=2026-09&to_period=2026-09")
cmap = {r["name"]: r for r in cf["rows"]}
eq("现金流 销售商品收到 103000", cmap["销售商品、提供劳务收到的现金"]["amount"], 103000.0)
eq("现金流 购建固定资产支付 180000",
   cmap["购建固定资产、无形资产和其他非流动资产支付的现金"]["amount"], 180000.0)
eq("现金流 期末余额=账面", cf["balanced"], True)

print("== 9. 凭证汇总表 ==")
st, vs = api("GET", "/api/vouchers/summary?from_period=2026-09&to_period=2026-09")
eq("凭证汇总平衡", (st, vs["balanced"]), (200, True))
check("凭证张数>0", vs["count"] >= 10, f"count={vs['count']}")

print("== 10. 反结转 ==")
st, recs = api("GET", "/api/carryover/records?period=2026-09")
sales_rec = next(r for r in recs if r["kind"] == "sales_cost")
st, r = api("POST", f"/api/carryover/reverse/{sales_rec['id']}")
eq("反结转销售成本", (st, r.get("kind")), (200, "结转销售成本"))
st, inc = api("GET", "/api/reports/income?period=2026-09&mode=month")
imap = {r["name"]: r for r in inc["rows"]}
eq("反结转后营业成本为 0", imap["　减：营业成本"]["ytd"], 0.0)
st, bs2 = api("GET", "/api/reports/balance-sheet?period=2026-09")
eq("反结转后资产负债表仍平衡", (st, bs2["balanced"]), (200, True))
st, tb2 = api("GET", "/api/books/trial-balance?period=2026-09")
eq("反结转后试算平衡", tb2["balanced"], True)
# 重新结转回来
st, r = api("POST", "/api/carryover/sales_cost", {"period": "2026-09", "amount": 50000})
eq("重新结转销售成本", st, 200)

print("== 11. 结账 / 反结账 ==")
st, r = api("POST", "/api/carryover/close", {"period": "2026-09"})
eq("结账成功", (st, r.get("status")), (200, "closed"))
st, r = api("POST", "/api/vouchers", {
    "date": "2026-09-30", "entries": [
        {"account_id": acc_id["560204"], "summary": "结账后", "debit": 10},
        {"account_id": acc_id["1002"], "summary": "结账后", "credit": 10}]})
eq("结账后新增凭证被拒绝", st, 400)
st, r = api("POST", "/api/carryover/open", {"period": "2026-09"})
eq("反结账", (st, r.get("status")), (200, "open"))
st, r = api("POST", "/api/carryover/close", {"period": "2026-09"})
eq("再次结账", (st, r.get("status")), (200, "closed"))

print("== 12. Excel 导入导出 ==")
for path, name in [
    ("/api/data/export/vouchers?from_period=2026-09&to_period=2026-09", "凭证明细"),
    ("/api/data/export/book/general-ledger?period=2026-09", "总账"),
    ("/api/data/export/book/balance-table?period=2026-09", "余额表"),
    ("/api/data/export/book/detail?account_code=1002&from_period=2026-09&to_period=2026-09", "明细账"),
    ("/api/data/export/book/journal?from_period=2026-09&to_period=2026-09", "序时账"),
    ("/api/data/export/book/multi-column?account_code=5602&from_period=2026-09&to_period=2026-09", "多栏账"),
    ("/api/reports/export/balance-sheet?period=2026-09", "资产负债表"),
    ("/api/reports/export/income?period=2026-09&mode=month", "利润表"),
    ("/api/reports/export/cashflow?period=2026-09", "现金流量表"),
    ("/api/reports/export/voucher-summary?period=2026-09", "凭证汇总表"),
]:
    st, data = api("GET", path, raw=True)
    check(f"导出{name}", st == 200 and data[:2] == b"PK" and len(data) > 2000,
          f"st={st} len={len(data) if isinstance(data, bytes) else 0}")

# 导入模板 -> 修改 -> 导入
st, tpl = api("GET", "/api/data/template/vouchers", raw=True)
check("下载导入模板", st == 200 and tpl[:2] == b"PK")
from openpyxl import load_workbook, Workbook
wb = load_workbook(io.BytesIO(tpl))
ws = wb.active
ws.delete_rows(2, 10)
ws.append(["2026-08-05", "记", "期初建账-现金", "1001", 5000, 0, "", ""])
ws.append(["2026-08-05", "记", "期初建账-现金", "1002", 0, 5000, "", ""])
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)
boundary = "----testboundary42"
body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"import.xlsx\"\r\nContent-Type: "
        f"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode() \
    + buf.read() + f"\r\n--{boundary}--\r\n".encode()
req = urllib.request.Request(BASE + "/api/data/import/vouchers", data=body, method="POST")
req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
try:
    with urllib.request.urlopen(req) as r:
        imp = json.loads(r.read())
        check("Excel 导入凭证", r.status == 200 and imp["created"] == 1, str(imp))
except urllib.error.HTTPError as e:
    check("Excel 导入凭证", False, e.read().decode()[:200])

st, bt8 = api("GET", "/api/books/balance-table?period=2026-08")
check("导入后 2026-08 有数据", st == 200 and any(
    r["code"] == "1001" and r["period_debit"] == 5000 for r in bt8["rows"]))

print("== 13. 备份 / 恢复 ==")
st, dbfile = api("GET", "/api/data/backup/download", raw=True)
check("备份文件为 SQLite", st == 200 and dbfile[:15] == b"SQLite format 3",
      f"st={st} head={dbfile[:15] if isinstance(dbfile, bytes) else ''}")
boundary = "----backupboundary42"
body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"backup.db\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
    + dbfile + f"\r\n--{boundary}--\r\n".encode()
req = urllib.request.Request(BASE + "/api/data/backup/restore", data=body, method="POST")
req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
try:
    with urllib.request.urlopen(req) as r:
        res = json.loads(r.read())
        check("备份恢复", r.status == 200 and res.get("ok"), str(res))
except urllib.error.HTTPError as e:
    check("备份恢复", False, e.read().decode()[:200])
st, bs3 = api("GET", "/api/reports/balance-sheet?period=2026-09")
eq("恢复后报表一致", (st, bs3["balanced"]), (200, True))

print("\n" + "=" * 50)
print(f"通过 {PASS} 项，失败 {FAIL} 项")
if failures:
    print("失败明细：")
    for f in failures:
        print("  -", f)
sys.exit(1 if FAIL else 0)
