"""结转与反结转：销售成本、工资、折旧、摊销、损益、税金、所得税、免交增值税、结账"""
from sqlalchemy.orm import Session
from ..models import (
    Account, Voucher, VoucherEntry, CarryoverRecord, FixedAsset, IntangibleAsset, Period,
)
from . import ledger as L
from . import vouchers as V


def _acc(db: Session, code: str) -> Account:
    a = L.account_by_code(db, code)
    if not a:
        raise ValueError(f"科目不存在：{code}")
    return a


def _mk(db: Session, kind: str, period: str, date: str, entries: list, note: str = "") -> dict:
    v = V.create_voucher(db, date=date, vtype="转", entries=entries,
                         source="carryover", carryover_kind=kind, remark=note)
    rec = CarryoverRecord(kind=kind, period=period, voucher_id=v.id,
                          created_at=V.now_str(), note=note,
                          amount=L.r2(sum(e.get("debit", 0) for e in entries)))
    db.add(rec)
    db.flush()
    return {"record_id": rec.id, "voucher_id": v.id, "voucher_no": v.voucher_no,
            "amount": rec.amount}


def _period_date(period: str) -> str:
    return f"{period}-01" if len(period) == 7 else period


def _month_date(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    # 月末日期
    import calendar
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


# ---------- 预览 ----------

def preview_sales_cost(db: Session, period: str, amount: float = None):
    """结转销售成本：默认取上期结转金额提示，实际以传入金额为准"""
    prev = db.query(CarryoverRecord).filter(
        CarryoverRecord.kind == "sales_cost",
        CarryoverRecord.period < period,
        CarryoverRecord.status == "active",
    ).order_by(CarryoverRecord.period.desc()).first()
    income = L._code_net(db, "5001", to_period=period, from_period=period)
    return {
        "suggested_amount": L.r2(prev.amount) if prev else 0.0,
        "period_income": L.r2(-income),
        "expense_code": L.get_setting(db, "sales_cost_expense_account", "5401"),
        "credit_code": L.get_setting(db, "sales_cost_credit_account", "1405"),
    }


def preview_salary(db: Session, period: str):
    prev = db.query(CarryoverRecord).filter(
        CarryoverRecord.kind == "salary", CarryoverRecord.period < period,
        CarryoverRecord.status == "active",
    ).order_by(CarryoverRecord.period.desc()).first()
    return {
        "suggested_amount": L.r2(prev.amount) if prev else 0.0,
        "expense_code": L.get_setting(db, "salary_expense_account", "560201"),
        "payable_code": L.get_setting(db, "payable_salary_account", "221101"),
    }


def preview_depreciation(db: Session, period: str):
    items = []
    total = 0.0
    for fa in db.query(FixedAsset).filter(FixedAsset.in_use == 1).all():
        amt = L.r2(fa.original_value * (1 - (fa.residual_rate or 0)) / (fa.life_months or 1))
        total = L.r2(total + amt)
        items.append({"id": fa.id, "name": fa.name, "amount": amt,
                      "expense_code": fa.expense_account_code or
                      L.get_setting(db, "depreciation_expense_account", "560202")})
    return {"items": items, "total": total,
            "credit_code": "1602",
            "expense_code": L.get_setting(db, "depreciation_expense_account", "560202")}


def preview_amortization(db: Session, period: str):
    items = []
    total = 0.0
    for ia in db.query(IntangibleAsset).filter(IntangibleAsset.in_use == 1).all():
        amt = L.r2(ia.original_value / (ia.amort_months or 1))
        total = L.r2(total + amt)
        items.append({"id": ia.id, "name": ia.name, "amount": amt,
                      "expense_code": ia.expense_account_code or
                      L.get_setting(db, "amortization_expense_account", "560203")})
    return {"items": items, "total": total, "credit_code": "1702",
            "expense_code": L.get_setting(db, "amortization_expense_account", "560203")}


def preview_profit(db: Session, period: str):
    """结转本期损益：各损益科目本期发生净额"""
    comps = L.pl_components(db, period, period)
    lines = []
    total_income = total_expense = 0.0
    for a in db.query(Account).filter(Account.is_leaf == 1).all():
        if a.category not in ("income", "expense"):
            continue
        d, c = L._entry_sums(db, [a.id], period=period)
        net = L.r2(d - c)
        if abs(net) < 0.005:
            continue
        if a.category == "income":
            lines.append({"account_code": a.code, "account_name": a.name,
                          "direction": "income", "amount": L.r2(-net)})
            total_income = L.r2(total_income - net)
        else:
            lines.append({"account_code": a.code, "account_name": a.name,
                          "direction": "expense", "amount": net})
            total_expense = L.r2(total_expense + net)
    return {"lines": lines, "total_income": total_income,
            "total_expense": total_expense,
            "net_profit": L.r2(total_income - total_expense),
            "profit_code": L.get_setting(db, "profit_account", "3103")}


def preview_tax(db: Session, period: str):
    """计提税金：以本期应交增值税为基数（可传入自定义基数）"""
    vat_base = L.r2(L._code_net(db, L.get_setting(db, "vat_account", "222101"),
                                to_period=period, from_period=period))
    vat_base = -vat_base  # 贷方为正
    city_rate = float(L.get_setting(db, "city_tax_rate", "0.07"))
    edu_rate = float(L.get_setting(db, "edu_rate", "0.03"))
    local_rate = float(L.get_setting(db, "local_edu_rate", "0.02"))
    return {
        "vat_base": vat_base,
        "city_tax": L.r2(max(vat_base, 0) * city_rate),
        "edu_tax": L.r2(max(vat_base, 0) * edu_rate),
        "local_edu_tax": L.r2(max(vat_base, 0) * local_rate),
        "rates": {"city": city_rate, "edu": edu_rate, "local_edu": local_rate},
    }


def preview_income_tax(db: Session, period: str):
    """计提所得税：（本年累计利润总额 × 税率）− 本年已计提所得税（剔除结转损益凭证）"""
    comps = L.pl_components(db, f"{period[:4]}-01", period, exclude_kind="profit")
    total_profit = L.r2(comps["revenue"] - comps["cost"] - comps["tax_surcharge"]
                        - comps["selling"] - comps["admin"] - comps["finance"]
                        + comps["invest_income"] + comps["nonop_income"]
                        - comps["nonop_expense"])
    accrued = L.r2(L._code_net(db, "5801", to_period=period, from_period=f"{period[:4]}-01",
                               exclude_kind="profit"))
    rate = float(L.get_setting(db, "income_tax_rate", "0.25"))
    should = L.r2(max(total_profit, 0) * rate)
    return {"total_profit_ytd": total_profit, "accrued_ytd": accrued,
            "rate": rate, "should_accrue": should,
            "amount": L.r2(max(should - accrued, 0))}


def preview_vat_free(db: Session, period: str):
    """免交增值税：小规模纳税人销售额未达起征点时，将应交增值税转入营业外收入

    判定口径由设置 vat_free_basis 决定：month=按月（月销售额≤月限额）、
    quarter=按季（季销售额≤季限额）。默认按月。
    """
    taxpayer = L.get_setting(db, "taxpayer_type", "small")
    basis = L.get_setting(db, "vat_free_basis", "month")
    month_limit = float(L.get_setting(db, "vat_free_month_limit", "100000"))
    quarter_limit = float(L.get_setting(db, "vat_free_quarter_limit", "300000"))
    sales_month = L.r2(-L._code_net(db, "5001", to_period=period, from_period=period)
                       - L._code_net(db, "5051", to_period=period, from_period=period))
    q = (int(period[5:7]) - 1) // 3 + 1
    from_q = f"{period[:4]}-{(q - 1) * 3 + 1:02d}"
    sales_quarter = L.r2(-(L._code_net(db, "5001", to_period=period, from_period=from_q)
                           + L._code_net(db, "5051", to_period=period, from_period=from_q)))
    vat_amt = L.r2(-L._code_net(db, L.get_setting(db, "vat_account", "222101"),
                                to_period=period, from_period=period))
    ok_month = sales_month <= month_limit
    ok_quarter = sales_quarter <= quarter_limit
    eligible = taxpayer == "small" and (ok_month if basis == "month" else ok_quarter)
    return {
        "taxpayer_type": taxpayer, "basis": basis,
        "sales_month": sales_month, "sales_quarter": sales_quarter,
        "month_limit": month_limit, "quarter_limit": quarter_limit,
        "ok_month": ok_month, "ok_quarter": ok_quarter,
        "eligible": eligible,
        "vat_amount": vat_amt,
        "vat_code": L.get_setting(db, "vat_account", "222101"),
        "income_code": "5301",
    }


# ---------- 执行 ----------

def do_sales_cost(db, period, amount: float, summary: str = "结转本月销售成本"):
    if amount <= 0:
        raise ValueError("结转金额必须大于 0")
    exp = L.get_setting(db, "sales_cost_expense_account", "5401")
    cred = L.get_setting(db, "sales_cost_credit_account", "1405")
    entries = [
        {"account_id": _acc(db, exp).id, "summary": summary, "debit": L.r2(amount)},
        {"account_id": _acc(db, cred).id, "summary": summary, "credit": L.r2(amount)},
    ]
    return _mk(db, "sales_cost", period, _month_date(period), entries, summary)


def do_salary(db, period, amount: float, expense_code: str = None,
              summary: str = "计提本月职工工资"):
    if amount <= 0:
        raise ValueError("计提金额必须大于 0")
    exp = expense_code or L.get_setting(db, "salary_expense_account", "560201")
    payable = L.get_setting(db, "payable_salary_account", "221101")
    entries = [
        {"account_id": _acc(db, exp).id, "summary": summary, "debit": L.r2(amount)},
        {"account_id": _acc(db, payable).id, "summary": summary, "credit": L.r2(amount)},
    ]
    return _mk(db, "salary", period, _month_date(period), entries, summary)


def do_depreciation(db, period, summary: str = "计提本月固定资产折旧"):
    prev = preview_depreciation(db, period)
    if not prev["items"]:
        raise ValueError("尚未录入固定资产，请先在财税设置中添加固定资产")
    entries = []
    for it in prev["items"]:
        if it["amount"] <= 0:
            continue
        entries.append({"account_id": _acc(db, it["expense_code"]).id,
                        "summary": f"{summary}（{it['name']}）", "debit": it["amount"]})
    if not entries:
        raise ValueError("本月折旧金额为 0")
    entries.append({"account_id": _acc(db, "1602").id, "summary": summary,
                    "credit": prev["total"]})
    return _mk(db, "depreciation", period, _month_date(period), entries, summary)


def do_amortization(db, period, summary: str = "摊销本月无形资产"):
    prev = preview_amortization(db, period)
    if not prev["items"]:
        raise ValueError("尚未录入无形资产，请先在财税设置中添加无形资产")
    entries = []
    for it in prev["items"]:
        if it["amount"] <= 0:
            continue
        entries.append({"account_id": _acc(db, it["expense_code"]).id,
                        "summary": f"{summary}（{it['name']}）", "debit": it["amount"]})
    if not entries:
        raise ValueError("本月摊销金额为 0")
    entries.append({"account_id": _acc(db, "1702").id, "summary": summary,
                    "credit": prev["total"]})
    return _mk(db, "amortization", period, _month_date(period), entries, summary)


def do_profit(db, period, summary: str = "结转本期损益"):
    prev = preview_profit(db, period)
    if not prev["lines"]:
        raise ValueError("本期没有需要结转的损益科目发生额")
    profit_acc = _acc(db, L.get_setting(db, "profit_account", "3103"))
    entries = []
    total_income = total_expense = 0.0
    for line in prev["lines"]:
        if line["direction"] == "income":
            entries.append({"account_id": _acc(db, line["account_code"]).id,
                            "summary": summary, "debit": line["amount"]})
            total_income = L.r2(total_income + line["amount"])
        else:
            entries.append({"account_id": _acc(db, line["account_code"]).id,
                            "summary": summary, "credit": line["amount"]})
            total_expense = L.r2(total_expense + line["amount"])
    net = L.r2(total_income - total_expense)
    if net >= 0:
        entries.append({"account_id": profit_acc.id, "summary": summary, "credit": net})
    else:
        entries.append({"account_id": profit_acc.id, "summary": summary, "debit": L.r2(-net)})
    return _mk(db, "profit", period, _month_date(period), entries,
               f"结转本期损益，净额 {net:.2f}")


def do_tax(db, period, vat_base: float = None, summary: str = "计提本月税金"):
    pv = preview_tax(db, period)
    base = L.r2(vat_base) if vat_base is not None else pv["vat_base"]
    if base <= 0:
        raise ValueError("计税基数（本期应交增值税）不大于 0，无需计提税金")
    city_rate = pv["rates"]["city"]
    edu_rate = pv["rates"]["edu"]
    local_rate = pv["rates"]["local_edu"]
    items = [("540301", "222106", L.r2(base * city_rate), "城市维护建设税"),
             ("540302", "222108", L.r2(base * edu_rate), "教育费附加"),
             ("540303", "222109", L.r2(base * local_rate), "地方教育附加")]
    entries = []
    total = 0.0
    for exp_code, liab_code, amt, name in items:
        if amt <= 0:
            continue
        entries.append({"account_id": _acc(db, exp_code).id,
                        "summary": f"{summary}——{name}", "debit": amt})
        entries.append({"account_id": _acc(db, liab_code).id,
                        "summary": f"{summary}——{name}", "credit": amt})
        total = L.r2(total + amt)
    if not entries:
        raise ValueError("税金金额为 0")
    return _mk(db, "tax", period, _month_date(period), entries,
               f"计税基数 {base:.2f}，合计 {total:.2f}")


def do_income_tax(db, period, amount: float = None, summary: str = "计提本月所得税费用"):
    pv = preview_income_tax(db, period)
    amt = L.r2(amount) if amount is not None else pv["amount"]
    if amt <= 0:
        raise ValueError("本期无需计提所得税（累计应计提 ≤ 已计提）")
    entries = [
        {"account_id": _acc(db, "5801").id, "summary": summary, "debit": amt},
        {"account_id": _acc(db, "222112").id, "summary": summary, "credit": amt},
    ]
    return _mk(db, "income_tax", period, _month_date(period), entries,
               f"累计利润 {pv['total_profit_ytd']:.2f}，税率 {pv['rate']}")


def do_vat_free(db, period, amount: float = None, summary: str = "小规模纳税人免征增值税"):
    pv = preview_vat_free(db, period)
    if pv["taxpayer_type"] != "small":
        raise ValueError("当前为一般纳税人，不适用小规模免征增值税处理")
    if not pv["eligible"]:
        raise ValueError(
            f"本期销售额未达免征条件（口径：{'按月' if pv['basis'] == 'month' else '按季'}）："
            f"本月销售额 {pv['sales_month']:.2f}（限额 {pv['month_limit']:.2f}），"
            f"本季销售额 {pv['sales_quarter']:.2f}（限额 {pv['quarter_limit']:.2f}）")
    amt = L.r2(amount) if amount is not None else pv["vat_amount"]
    if amt <= 0:
        raise ValueError("本期应交增值税 ≤ 0，无可免交金额")
    entries = [
        {"account_id": _acc(db, pv["vat_code"]).id, "summary": summary, "debit": amt},
        {"account_id": _acc(db, pv["income_code"]).id, "summary": summary, "credit": amt},
    ]
    return _mk(db, "vat_free", period, _month_date(period), entries,
               f"免征增值税 {amt:.2f} 转入营业外收入")


# ---------- 结转记录 / 反结转 ----------

def list_records(db: Session, period: str = None):
    q = db.query(CarryoverRecord).order_by(CarryoverRecord.period.desc(), CarryoverRecord.id.desc())
    if period:
        q = q.filter(CarryoverRecord.period == period)
    out = []
    for r in q.all():
        v = db.query(Voucher).get(r.voucher_id)
        out.append({
            "id": r.id, "kind": r.kind, "period": r.period, "amount": r.amount,
            "status": r.status, "created_at": r.created_at, "note": r.note,
            "voucher_id": r.voucher_id, "voucher_no": v.voucher_no if v else "",
        })
    return out


KIND_NAMES = {
    "sales_cost": "结转销售成本", "salary": "计提工资", "depreciation": "计提折旧",
    "amortization": "摊销无形资产", "profit": "结转本期损益", "tax": "计提税金",
    "income_tax": "计提所得税", "vat_free": "免交增值税",
}


def reverse(db: Session, record_id: int):
    """反结转：作废该结转生成的凭证"""
    rec = db.query(CarryoverRecord).get(record_id)
    if not rec:
        raise ValueError("结转记录不存在")
    if rec.status == "reversed":
        raise ValueError("该结转已反结转")
    if V.is_period_closed(db, rec.period):
        raise ValueError(f"期间 {rec.period} 已结账，请先反结账")
    v = db.query(Voucher).get(rec.voucher_id)
    if v:
        v.status = "voided"
    rec.status = "reversed"
    return {"record_id": rec.id, "voucher_no": v.voucher_no if v else "",
            "kind": KIND_NAMES.get(rec.kind, rec.kind)}


# ---------- 结账 / 反结账 ----------

def close_period(db: Session, period: str, force: bool = False):
    if not L.valid_period(period):
        raise ValueError(f"期间格式错误：{period}")
    tb = L.trial_balance(db, period)
    if not tb["balanced"]:
        raise ValueError(
            f"试算不平衡：借方合计 {tb['total_debit']:.2f} ≠ 贷方合计 {tb['total_credit']:.2f}，不能结账")
    drafts = db.query(Voucher).filter(
        Voucher.period == period, Voucher.status == "draft").count()
    if drafts:
        raise ValueError(f"期间 {period} 还有 {drafts} 张草稿凭证未审核记账")
    if not force:
        pl = L.profit_net(db, period, period)
        if abs(pl) >= 0.005:
            raise ValueError(
                f"本期损益尚未结平（本期净利润 {pl:.2f}），请先执行【结转本期损益】，或使用强制结账")
    p = V.ensure_period(db, period)
    p.status = "closed"
    p.closed_at = V.now_str()
    return {"period": period, "status": "closed"}


def open_period(db: Session, period: str):
    p = db.query(Period).filter(Period.period == period).first()
    if not p:
        raise ValueError(f"期间 {period} 不存在")
    p.status = "open"
    p.closed_at = ""
    return {"period": period, "status": "open"}
