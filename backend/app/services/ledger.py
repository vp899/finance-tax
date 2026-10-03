"""核心会计计算：余额、账簿、报表。

设计原则：
- 所有金额 r2() 保留 2 位小数。
- 借方为正的净额 net = 借 - 贷。
- 负债/权益/收入类以贷方为正列示（= -net）。
- 只有叶子科目允许记账/录入期初，汇总按科目编码前缀上卷。
- 报表恒等式：Σ全部科目净额 = 0 ⇒ 资产 = 负债 + 所有者权益 + 本期净利润，
  其中 未分配利润 = 3103+3104(贷方) + 未结转本年损益净额，保证任何结转状态下资产负债表均平衡。
"""
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Account, Voucher, VoucherEntry, OpeningBalance, Setting, CashflowItem,
)


def r2(x) -> float:
    return float(Decimal(str(x if x is not None else 0)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s and s.value not in (None, "") else default


def valid_period(period: str) -> bool:
    if not period or len(period) != 7 or period[4] != "-":
        return False
    try:
        y, m = int(period[:4]), int(period[5:7])
        return 1 <= m <= 12 and y > 1990
    except ValueError:
        return False


def period_range(from_period: str, to_period: str):
    if not valid_period(from_period) or not valid_period(to_period) or from_period > to_period:
        return []
    out, y, m = [], int(from_period[:4]), int(from_period[5:7])
    ty, tm = int(to_period[:4]), int(to_period[5:7])
    while (y, m) <= (ty, tm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def account_by_code(db: Session, code: str):
    return db.query(Account).filter(Account.code == code).first()


# 标准收入科目家族（损益类-收入）
INCOME_CODE_PREFIXES = ("5001", "5051", "5111", "5301")


def infer_category(code: str, direction: str = "D") -> str:
    """按科目编码推断核算类型：资产/负债/权益/成本/损益（收入/费用）"""
    c = (code or "")[:1]
    if c == "1":
        return "asset"
    if c == "2":
        return "liability"
    if c == "3":
        return "equity"
    if c == "4":
        return "cost"
    if code.startswith(INCOME_CODE_PREFIXES):
        return "income"
    return "expense"


def account_ids_for(db: Session, code: str, rollup: bool = True) -> list:
    acc = account_by_code(db, code)
    if not acc:
        return []
    if not rollup:
        return [acc.id]
    return [a.id for a in db.query(Account).filter(Account.code.like(f"{code}%")).all()]


def _entry_sums(db: Session, ids, from_period=None, to_period=None, period=None,
                exclude_kind=None):
    q = db.query(
        func.coalesce(func.sum(VoucherEntry.debit), 0.0),
        func.coalesce(func.sum(VoucherEntry.credit), 0.0),
    ).join(Voucher, Voucher.id == VoucherEntry.voucher_id).filter(
        VoucherEntry.account_id.in_(ids), Voucher.status == "posted"
    )
    if exclude_kind:
        q = q.filter((Voucher.carryover_kind.is_(None)) | (Voucher.carryover_kind != exclude_kind))
    if period:
        q = q.filter(Voucher.period == period)
    else:
        if from_period:
            q = q.filter(Voucher.period >= from_period)
        if to_period:
            q = q.filter(Voucher.period <= to_period)
    d, c = q.one()
    return r2(d or 0), r2(c or 0)


def opening_anchor_year(db: Session, before_period: str) -> str:
    """期初锚定年度：取 ≤ before_period 年份的最近一个已录入期初的年度。

    - 正常逐年录入期初时，锚定年度 = 当前年度（与旧行为一致）。
    - 若新年度尚未录入期初（期初自动结转的场景），锚定到最近有期初的年度，
      发生额从锚定年度年初连续累计，避免新年度余额被错误清零。
    """
    year = before_period[:4]
    row = (db.query(OpeningBalance.year)
           .filter(OpeningBalance.year <= year)
           .order_by(OpeningBalance.year.desc())
           .first())
    return row[0] if row else year


def net_side(od: float, oc: float):
    """借/贷毛额 → 单边余额（余额表期初/期末口径：余额只列在余额方向一侧）"""
    net = r2((od or 0) - (oc or 0))
    return (net, 0.0) if net >= 0 else (0.0, -net)


def opening_sums(db: Session, ids, before_period: str):
    """before_period 之前的期初 + 发生额（跨年锚定到最近有期初的年度）"""
    anchor = opening_anchor_year(db, before_period)
    ob = db.query(
        func.coalesce(func.sum(OpeningBalance.debit), 0.0),
        func.coalesce(func.sum(OpeningBalance.credit), 0.0),
    ).filter(OpeningBalance.account_id.in_(ids), OpeningBalance.year == anchor).one()
    od, oc = r2(ob[0] or 0), r2(ob[1] or 0)
    q = db.query(
        func.coalesce(func.sum(VoucherEntry.debit), 0.0),
        func.coalesce(func.sum(VoucherEntry.credit), 0.0),
    ).join(Voucher, Voucher.id == VoucherEntry.voucher_id).filter(
        VoucherEntry.account_id.in_(ids), Voucher.status == "posted",
        Voucher.period >= f"{anchor}-01", Voucher.period < before_period,
    )
    d, c = q.one()
    return r2(od + (d or 0)), r2(oc + (c or 0))


def balance_block(db: Session, ids, period=None, from_period=None, to_period=None):
    start = period or from_period or f"{to_period[:4]}-01"
    od, oc = opening_sums(db, ids, start)
    pd, pc = _entry_sums(db, ids, from_period=from_period, to_period=to_period, period=period)
    if period:
        pd, pc = _entry_sums(db, ids, period=period)
    net = r2((od + pd) - (oc + pc))
    cd, cc = (net, 0.0) if net >= 0 else (0.0, -net)
    # 期初按余额口径列示（单边），避免把区间前的借贷累计发生额当成期初余额
    odn, ocn = net_side(od, oc)
    return {
        "opening_debit": odn, "opening_credit": ocn,
        "period_debit": pd, "period_credit": pc,
        "closing_debit": cd, "closing_credit": cc,
    }


def signed_balance(db: Session, ids, to_period: str) -> float:
    """截至 to_period 期末的净额（借方为正）。

    期初余额按年度存放，因此发生额必须限定在同一年度内，
    否则跨年数据会把以前年度分录重复计入。
    """
    year_start = f"{to_period[:4]}-01"
    od, oc = opening_sums(db, ids, year_start)
    d, c = _entry_sums(db, ids, from_period=year_start, to_period=to_period)
    return r2((od + d) - (oc + c))


def all_time_balance(db: Session, ids) -> float:
    """全部期初 + 全部发生额的净额（借方为正）"""
    ob = db.query(
        func.coalesce(func.sum(OpeningBalance.debit), 0.0),
        func.coalesce(func.sum(OpeningBalance.credit), 0.0),
    ).filter(OpeningBalance.account_id.in_(ids)).one()
    d, c = _entry_sums(db, ids)
    return r2((ob[0] or 0) + d - (ob[1] or 0) - c)


# ---------------- 账簿 ----------------

def general_ledger(db: Session, period: str = None, from_period: str = None,
                   to_period: str = None):
    rows = []
    for a in db.query(Account).order_by(Account.code).all():
        ids = account_ids_for(db, a.code, rollup=True)
        b = balance_block(db, ids, period=period, from_period=from_period,
                          to_period=to_period)
        rows.append({"code": a.code, "name": a.name, "level": a.level,
                     "direction": a.direction, **b})
    return rows


def balance_table(db: Session, period: str = None, from_period: str = None,
                  to_period: str = None):
    return general_ledger(db, period=period, from_period=from_period,
                          to_period=to_period)


def detail_ledger(db: Session, code: str, from_period: str, to_period: str, rollup: bool = True):
    acc = account_by_code(db, code)
    if not acc:
        return {"account": None, "opening": {"debit": 0, "credit": 0}, "rows": []}
    ids = account_ids_for(db, code, rollup=rollup)
    od, oc = opening_sums(db, ids, from_period)
    odn, ocn = net_side(od, oc)
    acc_map = {a.id: a for a in db.query(Account).all()}
    rows = []
    net = r2(od - oc)
    entries = db.query(VoucherEntry, Voucher).join(
        Voucher, Voucher.id == VoucherEntry.voucher_id
    ).filter(
        VoucherEntry.account_id.in_(ids), Voucher.status == "posted",
        Voucher.period >= from_period, Voucher.period <= to_period,
    ).order_by(Voucher.date, Voucher.voucher_no, VoucherEntry.line_no).all()
    for e, v in entries:
        net = r2(net + e.debit - e.credit)
        rows.append({
            "date": v.date, "period": v.period, "voucher_no": v.voucher_no,
            "source_no": v.source_no or "",
            "summary": e.summary, "account_code": acc_map[e.account_id].code,
            "account_name": acc_map[e.account_id].name,
            "debit": e.debit, "credit": e.credit,
            "balance_debit": net if net >= 0 else 0.0,
            "balance_credit": -net if net < 0 else 0.0,
        })
    return {"account": {"code": acc.code, "name": acc.name, "direction": acc.direction},
            "opening": {"debit": odn, "credit": ocn}, "rows": rows}


def journal(db: Session, from_period: str, to_period: str):
    acc_map = {a.id: a for a in db.query(Account).all()}
    entries = db.query(VoucherEntry, Voucher).join(
        Voucher, Voucher.id == VoucherEntry.voucher_id
    ).filter(
        Voucher.status == "posted",
        Voucher.period >= from_period, Voucher.period <= to_period,
    ).order_by(Voucher.date, Voucher.voucher_no, VoucherEntry.line_no).all()
    rows = []
    for e, v in entries:
        a = acc_map[e.account_id]
        rows.append({
            "date": v.date, "period": v.period, "voucher_no": v.voucher_no,
            "source_no": v.source_no or "",
            "vtype": v.vtype, "summary": e.summary,
            "account_code": a.code, "account_name": a.name,
            "debit": e.debit, "credit": e.credit,
            "quantity": e.quantity, "unit": e.unit,
        })
    return rows


def multi_column_ledger(db: Session, code: str, from_period: str, to_period: str):
    acc = account_by_code(db, code)
    if not acc:
        return {"account": None, "columns": [], "rows": [], "total": {}}
    children = db.query(Account).filter(Account.parent_code == code).order_by(Account.code).all()
    if not children:
        children = [acc]
    col_map = {a.id: a for a in children}
    entries = db.query(VoucherEntry, Voucher).join(
        Voucher, Voucher.id == VoucherEntry.voucher_id
    ).filter(
        VoucherEntry.account_id.in_(list(col_map.keys())), Voucher.status == "posted",
        Voucher.period >= from_period, Voucher.period <= to_period,
    ).order_by(Voucher.date, Voucher.voucher_no, VoucherEntry.line_no).all()
    rows = []
    for e, v in entries:
        a = col_map[e.account_id]
        cols = {c.code: 0.0 for c in children}
        cols[a.code] = r2(e.debit - e.credit)
        rows.append({
            "date": v.date, "voucher_no": v.voucher_no, "summary": e.summary,
            "account_code": a.code, "account_name": a.name,
            "columns": cols, "debit": e.debit, "credit": e.credit,
        })
    total = {c.code: r2(sum(r["columns"][c.code] for r in rows)) for c in children}
    return {"account": {"code": acc.code, "name": acc.name},
            "columns": [{"code": c.code, "name": c.name} for c in children],
            "rows": rows, "total": total}


def trial_balance(db: Session, period: str = None, from_period: str = None,
                  to_period: str = None):
    """试算平衡表（支持单期间或起止区间）。

    口径：
    - 覆盖全部末级科目，以及历史上被直接记账/录入期初的非末级科目，
      保证 Σ期初 + Σ发生 始终纳入合计，避免个别科目被漏计导致“试算不平衡”。
    - 期初 = 区间开始前余额（跨年锚定），本期 = 区间发生额，期末 = 期初 + 本期。
    """
    to_period = to_period or period
    from_period = from_period or to_period
    if not (valid_period(from_period) and valid_period(to_period)) or from_period > to_period:
        raise ValueError("期间格式应为 YYYY-MM，且起始期间不能晚于截止期间")

    # 科目范围：全部末级 + 有期初/发生额的非末级（历史数据兜底）
    scope = []
    for a in db.query(Account).order_by(Account.code).all():
        if a.is_leaf:
            scope.append(a)
            continue
        ob = (db.query(OpeningBalance.id)
              .filter(OpeningBalance.account_id == a.id).first())
        if ob:
            scope.append(a)
            continue
        d, c = _entry_sums(db, [a.id], from_period=from_period, to_period=to_period)
        if d or c:
            scope.append(a)

    td = tc = 0.0
    tod = toc = tpd = tpc = 0.0
    rows = []
    for a in scope:
        od, oc = opening_sums(db, [a.id], from_period)
        pd, pc = _entry_sums(db, [a.id], from_period=from_period, to_period=to_period)
        net = r2((od + pd) - (oc + pc))
        d = net if net > 0 else 0.0
        c = -net if net < 0 else 0.0
        td, tc = r2(td + d), r2(tc + c)
        odn, ocn = net_side(od, oc)
        tod, toc = r2(tod + odn), r2(toc + ocn)
        tpd, tpc = r2(tpd + pd), r2(tpc + pc)
        rows.append({
            "code": a.code, "name": a.name, "debit": d, "credit": c,
            "is_leaf": bool(a.is_leaf),
            "opening_debit": odn, "opening_credit": ocn,
            "period_debit": pd, "period_credit": pc,
            "closing_debit": d, "closing_credit": c,
        })
    return {"rows": rows, "total_debit": td, "total_credit": tc,
            "total_opening_debit": tod, "total_opening_credit": toc,
            "total_period_debit": tpd, "total_period_credit": tpc,
            "balanced": abs(td - tc) < 0.005,
            "difference": r2(td - tc),
            "period": to_period, "from_period": from_period, "to_period": to_period}


# ---------------- 报表 ----------------

def _code_net(db: Session, code: str, to_period: str = None, from_period: str = None,
              exclude_kind: str = None) -> float:
    """科目（含下级）净额；to_period 截止余额，或 from..to 区间发生净额"""
    ids = account_ids_for(db, code, rollup=True)
    if not ids:
        return 0.0
    if from_period is not None:
        d, c = _entry_sums(db, ids, from_period=from_period, to_period=to_period,
                           exclude_kind=exclude_kind)
        return r2(d - c)
    return signed_balance(db, ids, to_period=to_period)


def _leaf_sum(db: Session, predicate, to_period=None, from_period=None,
              exclude_kind=None) -> float:
    total = 0.0
    for a in db.query(Account).filter(Account.is_leaf == 1).all():
        if predicate(a):
            if from_period is not None:
                d, c = _entry_sums(db, [a.id], from_period=from_period,
                                   to_period=to_period, exclude_kind=exclude_kind)
                total = r2(total + (d - c))
            else:
                total = r2(total + signed_balance(db, [a.id], to_period=to_period))
    return total


def pl_components(db: Session, from_period: str, to_period: str, exclude_kind: str = None):
    """损益类各组成（发生净额；收入类为贷方正，费用类为借方正）

    exclude_kind="profit" 时剔除结转损益凭证，用于利润表/所得税计提，
    使结转后报表仍能反映真实经营成果。
    """
    def move(code, sign):
        v = _code_net(db, code, to_period=to_period, from_period=from_period,
                      exclude_kind=exclude_kind)
        return v if sign == "D" else r2(-v)

    def cat_move(pred, sign):
        v = _leaf_sum(db, pred, to_period=to_period, from_period=from_period,
                      exclude_kind=exclude_kind)
        return v if sign == "D" else r2(-v)

    is_income = lambda a: a.category == "income"
    is_expense = lambda a: a.category == "expense"
    revenue = cat_move(lambda a: is_income(a) and not a.code.startswith(("5111", "5301")), "C")
    cost = cat_move(lambda a: is_expense(a) and not a.code.startswith(("5403", "5601", "5602", "5603", "5711", "5801")), "D")
    return {
        "revenue": revenue,
        "cost": cost,
        "tax_surcharge": move("5403", "D"),
        "selling": move("5601", "D"),
        "admin": move("5602", "D"),
        "finance": move("5603", "D"),
        "invest_income": move("5111", "C"),
        "nonop_income": move("5301", "C"),
        "nonop_expense": move("5711", "D"),
        "income_tax": move("5801", "D"),
    }


def profit_net(db: Session, from_period: str, to_period: str) -> float:
    p = pl_components(db, from_period, to_period)
    return r2(p["revenue"] - p["cost"] - p["tax_surcharge"] - p["selling"]
              - p["admin"] - p["finance"] + p["invest_income"] + p["nonop_income"]
              - p["nonop_expense"] - p["income_tax"])


def profit_net_ytd(db: Session, to_period: str) -> float:
    return profit_net(db, f"{to_period[:4]}-01", to_period)


INCOME_ROWS = [
    ("一、营业收入", "revenue", 1),
    ("　减：营业成本", "cost", -1),
    ("　　　营业税金及附加", "tax_surcharge", -1),
    ("　　　销售费用", "selling", -1),
    ("　　　管理费用", "admin", -1),
    ("　　　财务费用", "finance", -1),
    ("　加：投资收益（损失以“-”号填列）", "invest_income", 1),
    ("二、营业利润（亏损以“-”号填列）", "op_profit", None),
    ("　加：营业外收入", "nonop_income", 1),
    ("　减：营业外支出", "nonop_expense", -1),
    ("三、利润总额（亏损以“-”号填列）", "total_profit", None),
    ("　减：所得税费用", "income_tax", -1),
    ("四、净利润（净亏损以“-”号填列）", "net_profit", None),
]


def _build_income_rows(p: dict):
    rows, calc = [], {}
    for name, key, sign in INCOME_ROWS:
        if sign is not None:
            v = r2(p[key])
            calc[key] = v
            rows.append({"name": name, "value": v, "type": "line"})
        elif key == "op_profit":
            v = r2(calc["revenue"] - calc["cost"] - calc["tax_surcharge"]
                   - calc["selling"] - calc["admin"] - calc["finance"] + calc["invest_income"])
            rows.append({"name": name, "value": v, "type": "calc"})
            calc[key] = v
        elif key == "total_profit":
            v = r2(calc["op_profit"] + calc["nonop_income"] - calc["nonop_expense"])
            rows.append({"name": name, "value": v, "type": "calc"})
            calc[key] = v
        else:
            v = r2(calc["total_profit"] - calc["income_tax"])
            rows.append({"name": name, "value": v, "type": "calc"})
            calc[key] = v
    return rows


def income_statement(db: Session, period: str, mode: str = "month",
                     from_period: str = None, to_period: str = None):
    """利润表 / 利润表季报 / 区间利润表（剔除结转损益凭证，结转后仍显示真实成果）

    mode=month   当期=本月，本年累计=年初至今
    mode=quarter 当期=本季，本年累计=年初至今
    mode=range   当期=from_period..to_period 区间合计，本年累计=年初至 to_period
    """
    year = period[:4]
    if mode == "range" and from_period and to_period:
        cur_rows = _build_income_rows(
            pl_components(db, from_period, to_period, exclude_kind="profit"))
        from_p = f"{to_period[:4]}-01"
    elif mode == "quarter":
        q = (int(period[5:7]) - 1) // 3 + 1
        from_p = f"{year}-{(q - 1) * 3 + 1:02d}"
        cur_rows = _build_income_rows(pl_components(db, period, period, exclude_kind="profit"))
    else:
        from_p = f"{year}-01"
        cur_rows = _build_income_rows(pl_components(db, period, period, exclude_kind="profit"))
    ytd_rows = _build_income_rows(pl_components(db, from_p, to_period or period,
                                                exclude_kind="profit"))
    seq_rows = cur_rows if mode == "range" else ytd_rows
    rows = [{
        "name": c["name"],
        "current": c["value"], "ytd": y["value"], "quarter": s["value"],
        "type": c["type"],
    } for c, y, s in zip(cur_rows, ytd_rows, seq_rows)]
    return {"rows": rows, "period": period, "mode": mode,
            "from_period": from_period or from_p, "to_period": to_period or period,
            "net_profit_ytd": ytd_rows[-1]["value"]}


# 资产负债表行定义
BS_ROWS = [
    ("line", "货币资金", "asset_cur", ["1001", "1002", "1012"]),
    ("line", "应收票据", "asset_cur", ["1121"]),
    ("line", "应收账款", "asset_cur", ["1122"]),
    ("line", "预付账款", "asset_cur", ["1123"]),
    ("line", "应收股利", "asset_cur", ["1131"]),
    ("line", "应收利息", "asset_cur", ["1132"]),
    ("line", "其他应收款", "asset_cur", ["1221"]),
    ("line", "存货", "asset_cur", ["1401", "1402", "1403", "1404", "1405", "1406", "1407", "1408", "1411"]),
    ("line", "短期投资", "asset_cur", ["1101"]),
    ("line", "其他流动资产", "asset_cur", ["1901"]),
    ("sub", "流动资产合计", "asset_cur"),
    ("line", "长期债券投资", "asset_ncur", ["1501"]),
    ("line", "长期股权投资", "asset_ncur", ["1511"]),
    ("line", "固定资产净额", "asset_ncur", ["1601", "1602"]),
    ("line", "在建工程", "asset_ncur", ["1604"]),
    ("line", "工程物资", "asset_ncur", ["1605"]),
    ("line", "固定资产清理", "asset_ncur", ["1606"]),
    ("line", "无形资产", "asset_ncur", ["1701", "1702"]),
    ("line", "长期待摊费用", "asset_ncur", ["1801"]),
    ("sub", "非流动资产合计", "asset_ncur"),
    ("total", "资产总计", "asset_total"),
    ("line", "短期借款", "liab_cur", ["2001"]),
    ("line", "应付票据", "liab_cur", ["2201"]),
    ("line", "应付账款", "liab_cur", ["2202"]),
    ("line", "预收账款", "liab_cur", ["2203"]),
    ("line", "应付职工薪酬", "liab_cur", ["2211"]),
    ("line", "应交税费", "liab_cur", ["2221"]),
    ("line", "应付利息", "liab_cur", ["2231"]),
    ("line", "应付股利", "liab_cur", ["2232"]),
    ("line", "其他应付款", "liab_cur", ["2241"]),
    ("sub", "流动负债合计", "liab_cur"),
    ("line", "长期借款", "liab_ncur", ["2501"]),
    ("line", "长期应付款", "liab_ncur", ["2701"]),
    ("line", "递延收益", "liab_ncur", ["2401"]),
    ("sub", "非流动负债合计", "liab_ncur"),
    ("sub", "负债合计", "liab_total"),
    ("line", "实收资本", "equity", ["3001"]),
    ("line", "资本公积", "equity", ["3002"]),
    ("line", "盈余公积", "equity", ["3101"]),
    ("line", "未分配利润", "equity", ["__undistributed__"]),
    ("line", "其他权益", "equity", ["__other_equity__"]),
    ("sub", "所有者权益合计", "equity_total"),
    ("total", "负债和所有者权益总计", "le_total"),
]

BS_COVERED = set()
for _k, _n, _g, *_rest in BS_ROWS:
    if _k == "line":
        for _c in _rest[0]:
            if not _c.startswith("__"):
                BS_COVERED.add(_c)


def _line_value(db: Session, codes, to_period=None, from_period=None, beginning=False,
                extra: float = 0.0):
    if codes == ["__other_equity__"]:
        return r2(extra)
    if codes == ["__undistributed__"]:
        ids = account_ids_for(db, "3103") + account_ids_for(db, "3104")
        if beginning:
            d, c = opening_sums(db, ids, f"{to_period[:4]}-01")
            return r2(r2(-(d - c)) + extra)
        val = r2(-signed_balance(db, ids, to_period=to_period))
        if from_period is None and to_period:
            val = r2(val + profit_net_ytd(db, to_period))
        return r2(val + extra)
    total = r2(extra)
    for code in codes:
        if beginning:
            ids = account_ids_for(db, code, rollup=True)
            d, c = opening_sums(db, ids, f"{to_period[:4]}-01")
            total = r2(total + (d - c))
        elif from_period is not None:
            total = r2(total + _code_net(db, code, to_period=to_period, from_period=from_period))
        else:
            total = r2(total + _code_net(db, code, to_period=to_period))
    return total


def _bs_extras(db: Session, period: str, year: str):
    """报表行兕底金额：未被固定行覆盖的科目（用户自建科目/成本类）按类别归集，
    保证任意科目表下资产负债表恒等式依然成立。

    - 成本类（4xxx 生产成本/制造费用）→ 并入存货
    - 其他资产类 → 其他流动资产
    - 其他负债类 → 其他应付款
    - 其他权益类 → 其他权益
    返回 (期末 dict, 年初 dict)，key 为报表行名称。
    """
    covered = set()
    for kind, name, grp, *rest in BS_ROWS:
        if kind == "line":
            for code in rest[0]:
                if not code.startswith("__"):
                    covered.update(account_ids_for(db, code, rollup=True))
    covered.update(account_ids_for(db, "3103", rollup=True))
    covered.update(account_ids_for(db, "3104", rollup=True))
    names = {"cost": "存货", "asset": "其他流动资产",
             "liability": "其他应付款", "equity": "其他权益"}
    end = {v: 0.0 for v in names.values()}
    beg = {v: 0.0 for v in names.values()}
    year_start = f"{year}-01"
    for a in db.query(Account).filter(Account.is_leaf == 1).all():
        if a.id in covered or a.category in ("income", "expense"):
            continue
        name = names.get(a.category)
        if not name:
            continue
        net_end = signed_balance(db, [a.id], to_period=period)
        d, c = opening_sums(db, [a.id], year_start)
        end[name] = r2(end[name] + net_end)
        beg[name] = r2(beg[name] + r2(d - c))
    return end, beg


def balance_sheet(db: Session, period: str):
    year = period[:4]
    extra_end, extra_beg = _bs_extras(db, period, year)
    rows = []
    vals_end, vals_beg = {}, {}
    for kind, name, grp, *rest in BS_ROWS:
        if kind == "line":
            codes = rest[0]
            neg = grp in ("liab_cur", "liab_ncur", "equity") \
                and codes != ["__undistributed__"]
            e = _line_value(db, codes, to_period=period, extra=extra_end.get(name, 0.0))
            b = _line_value(db, codes, to_period=f"{year}-01", beginning=True,
                            extra=extra_beg.get(name, 0.0))
            if neg:  # 负债/权益类以贷方为正列示
                e, b = r2(-e), r2(-b)
            vals_end[name], vals_beg[name] = e, b
            rows.append({"name": name, "ending": e, "beginning": b,
                         "group": grp, "type": "line"})
        elif kind == "sub":
            keys = {
                "流动资产合计": ["asset_cur"], "非流动资产合计": ["asset_ncur"],
                "流动负债合计": ["liab_cur"], "非流动负债合计": ["liab_ncur"],
                "所有者权益合计": ["equity"],
            }
            if name in keys:
                e = r2(sum(r["ending"] for r in rows
                           if r["type"] == "line" and r["group"] in keys[name]))
                b = r2(sum(r["beginning"] for r in rows
                           if r["type"] == "line" and r["group"] in keys[name]))
            else:  # 负债合计
                e = r2(vals_end["流动负债合计"] + vals_end["非流动负债合计"])
                b = r2(vals_beg["流动负债合计"] + vals_beg["非流动负债合计"])
            vals_end[name], vals_beg[name] = e, b
            rows.append({"name": name, "ending": e, "beginning": b,
                         "group": grp, "type": "sub"})
        else:
            if name == "资产总计":
                e = r2(vals_end["流动资产合计"] + vals_end["非流动资产合计"])
                b = r2(vals_beg["流动资产合计"] + vals_beg["非流动资产合计"])
            else:
                e = r2(vals_end["负债合计"] + vals_end["所有者权益合计"])
                b = r2(vals_beg["负债合计"] + vals_beg["所有者权益合计"])
            vals_end[name], vals_beg[name] = e, b
            rows.append({"name": name, "ending": e, "beginning": b,
                         "group": grp, "type": "total"})
    return {"rows": rows, "period": period,
            "balanced": abs(vals_end["资产总计"] - (vals_end["负债合计"] + vals_end["所有者权益合计"])) < 0.01,
            "asset_total": vals_end["资产总计"],
            "liability_equity_total": r2(vals_end["负债合计"] + vals_end["所有者权益合计"])}


CASHFLOW_LINES = [
    ("item", "销售商品、提供劳务收到的现金", "101"),
    ("item", "收到的税费返还", "102"),
    ("item", "收到其他与经营活动有关的现金", "103"),
    ("sub", "经营活动现金流入小计", ["101", "102", "103"], "in"),
    ("item", "购买商品、接受劳务支付的现金", "201"),
    ("item", "支付给职工以及为职工支付的现金", "202"),
    ("item", "支付的各项税费", "203"),
    ("item", "支付其他与经营活动有关的现金", "204"),
    ("sub", "经营活动现金流出小计", ["201", "202", "203", "204"], "out"),
    ("calc", "经营活动产生的现金流量净额", "op_net"),
    ("item", "收回投资收到的现金", "301"),
    ("item", "取得投资收益收到的现金", "302"),
    ("item", "处置固定资产、无形资产和其他非流动资产收回的现金净额", "303"),
    ("item", "处置子公司及其他营业单位收到的现金净额", "304"),
    ("item", "收到其他与投资活动有关的现金", "305"),
    ("sub", "投资活动现金流入小计", ["301", "302", "303", "304", "305"], "in"),
    ("item", "购建固定资产、无形资产和其他非流动资产支付的现金", "401"),
    ("item", "投资支付的现金", "402"),
    ("item", "取得子公司及其他营业单位支付的现金净额", "403"),
    ("item", "支付其他与投资活动有关的现金", "404"),
    ("sub", "投资活动现金流出小计", ["401", "402", "403", "404"], "out"),
    ("calc", "投资活动产生的现金流量净额", "inv_net"),
    ("item", "吸收投资收到的现金", "501"),
    ("item", "取得借款收到的现金", "502"),
    ("item", "收到其他与筹资活动有关的现金", "503"),
    ("sub", "筹资活动现金流入小计", ["501", "502", "503"], "in"),
    ("item", "偿还债务支付的现金", "601"),
    ("item", "分配股利、利润或偿付利息支付的现金", "602"),
    ("item", "支付其他与筹资活动有关的现金", "603"),
    ("sub", "筹资活动现金流出小计", ["601", "602", "603"], "out"),
    ("calc", "筹资活动产生的现金流量净额", "fin_net"),
    ("calc", "现金及现金等价物净增加额", "net_inc"),
    ("calc", "加：期初现金及现金等价物余额", "begin_bal"),
    ("calc", "期末现金及现金等价物余额", "end_bal"),
]

CASH_CODES = ["1001", "1002", "1012"]


def cashflow_amounts(db: Session, from_period: str, to_period: str):
    """按现金流量项目汇总：(流入, 流出)"""
    ids = []
    for c in CASH_CODES:
        ids.extend(account_ids_for(db, c, rollup=True))
    result = {}
    entries = db.query(VoucherEntry, Voucher).join(
        Voucher, Voucher.id == VoucherEntry.voucher_id
    ).filter(
        VoucherEntry.account_id.in_(ids), Voucher.status == "posted",
        Voucher.period >= from_period, Voucher.period <= to_period,
    ).all()
    for e, v in entries:
        code = e.cashflow_code or "103"
        inflow, outflow = result.get(code, (0.0, 0.0))
        result[code] = (r2(inflow + e.debit), r2(outflow + e.credit))
    return result


def cashflow_statement(db: Session, from_period: str, to_period: str):
    amounts = cashflow_amounts(db, from_period, to_period)

    def item_val(code):
        inflow, outflow = amounts.get(code, (0.0, 0.0))
        return r2(inflow - outflow)  # 净流入为正

    rows, store = [], {}
    item_dir = {c.code: c.direction for c in db.query(CashflowItem).all()}
    for entry in CASHFLOW_LINES:
        kind, name = entry[0], entry[1]
        if kind == "item":
            v = item_val(entry[2])
            if item_dir.get(entry[2], "D") == "C":
                v = r2(-v)  # 流出类项目：支付额为正
            rows.append({"name": name, "amount": v, "type": "line"})
        elif kind == "sub":
            v = (r2(sum(max(item_val(c), 0.0) for c in entry[2])) if entry[3] == "in"
                 else r2(sum(max(-item_val(c), 0.0) for c in entry[2])))
            rows.append({"name": name, "amount": v, "type": "sub"})
        else:
            key = entry[2]
            if key == "op_net":
                v = r2(store["经营活动现金流入小计"] - store["经营活动现金流出小计"])
            elif key == "inv_net":
                v = r2(store["投资活动现金流入小计"] - store["投资活动现金流出小计"])
            elif key == "fin_net":
                v = r2(store["筹资活动现金流入小计"] - store["筹资活动现金流出小计"])
            elif key == "net_inc":
                v = r2(store["经营活动产生的现金流量净额"]
                       + store["投资活动产生的现金流量净额"]
                       + store["筹资活动产生的现金流量净额"])
            elif key == "begin_bal":
                ids = []
                for c in CASH_CODES:
                    ids.extend(account_ids_for(db, c, rollup=True))
                d, c = opening_sums(db, ids, from_period)
                v = r2(d - c)
            else:
                v = r2(store["加：期初现金及现金等价物余额"] + store["现金及现金等价物净增加额"])
            rows.append({"name": name, "amount": v, "type": "calc"})
        store[name] = rows[-1]["amount"]
    ids = []
    for c in CASH_CODES:
        ids.extend(account_ids_for(db, c, rollup=True))
    book_end = signed_balance(db, ids, to_period=to_period)
    return {"rows": rows, "from_period": from_period, "to_period": to_period,
            "book_ending_cash": book_end,
            "balanced": abs(book_end - store["期末现金及现金等价物余额"]) < 0.01}


def voucher_summary(db: Session, from_period: str, to_period: str):
    from ..models import Voucher as V
    vouchers = db.query(V).filter(
        V.status != "voided", V.period >= from_period, V.period <= to_period,
    ).order_by(V.period, V.vtype).all()
    agg = {}
    for v in vouchers:
        agg.setdefault(v.vtype, {"vtype": v.vtype, "count": 0, "debit": 0.0, "credit": 0.0})
        agg[v.vtype]["count"] += 1
        for e in v.entries:
            agg[v.vtype]["debit"] = r2(agg[v.vtype]["debit"] + e.debit)
            agg[v.vtype]["credit"] = r2(agg[v.vtype]["credit"] + e.credit)
    rows = list(agg.values())
    for r in rows:
        r["debit"], r["credit"] = r2(r["debit"]), r2(r["credit"])
    total_d = r2(sum(r["debit"] for r in rows))
    total_c = r2(sum(r["credit"] for r in rows))
    return {"rows": rows, "total_debit": total_d, "total_credit": total_c,
            "count": sum(r["count"] for r in rows),
            "balanced": abs(total_d - total_c) < 0.005}
