"""结转与反结转：18 步月末/年末结转 + 结转配置 + 一键结转 + 结账

结转步骤（默认顺序，可在结转配置中调整/停用）：
  1 结转销售成本        2 计提工资          2.1 发放工资
  3 发放全年一次性奖金   4 计提折旧          5 摊销无形资产
  6 摊销待摊费用        7 免交增值税         8 计提全年一次性奖金
  9 计提劳务报酬        10 发放劳务报酬      11 计提税金
  12 地方水利基金       13 印花税           14 工会经费
  15 计提所得税         16 结转汇兑损益      17 结转本期损益
  18 结转未分配利润

设计原则：
- 所有结转均生成借贷平衡的凭证（由 validate_entries 强制校验）。
- 自动金额步骤金额为 0 时跳过（一键结转不报错）。
- 科目可配置；配置的科目缺失/非末级时自动定位或创建明细科目。
"""
import calendar
import json

from sqlalchemy.orm import Session

from ..models import (
    Account, Currency, Voucher, VoucherEntry, CarryoverRecord,
    FixedAsset, IntangibleAsset, OpeningBalance, Period, Setting,
)
from . import ledger as L
from . import vouchers as V


# ---------- 基础工具 ----------

def _acc(db: Session, code: str) -> Account:
    a = L.account_by_code(db, code)
    if not a:
        raise ValueError(f"科目不存在：{code}")
    return a


def _next_child_code(db: Session, parent_code: str) -> str:
    codes = [a.code for a in db.query(Account).filter(
        Account.code.like(f"{parent_code}%")).all() if len(a.code) > len(parent_code)]
    max_seq = 0
    for c in codes:
        suffix = c[len(parent_code):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return f"{parent_code}{max_seq + 1:02d}"


def resolve_account(db: Session, code: str, *, name: str = None,
                    direction: str = "D", category: str = "expense") -> Account:
    """把配置的科目解析为可记账的末级科目。

    - 科目存在且为末级：直接使用。
    - 科目存在但为非末级：取同名下级，否则自动创建明细科目（如 5301 → 530102 免征增值税）。
    - 科目不存在：自动创建（挂在前缀上级下）。
    """
    a = L.account_by_code(db, code)
    if a and a.is_leaf:
        return a
    label = name or code
    if a:
        child = db.query(Account).filter(
            Account.parent_code == a.code, Account.name == label).first()
        if child and child.is_leaf:
            return child
        new_code = _next_child_code(db, a.code)
        n = Account(code=new_code, name=label, parent_code=a.code,
                    direction=direction, category=category, is_leaf=1,
                    level=a.level + 1, pinyin="")
        db.add(n)
        db.flush()
        return n
    parent_code = code[:4] if len(code) > 4 and L.account_by_code(db, code[:4]) else None
    parent = L.account_by_code(db, parent_code) if parent_code else None
    n = Account(code=code, name=label, parent_code=parent_code,
                direction=direction, category=category, is_leaf=1,
                level=(parent.level + 1) if parent else 1, pinyin="")
    db.add(n)
    db.flush()
    return n


def _mk(db: Session, kind: str, period: str, date: str, entries: list, note: str = "") -> dict:
    v = V.create_voucher(db, date=date, vtype="转", entries=entries,
                         source="carryover", carryover_kind=kind, remark=note)
    rec = CarryoverRecord(kind=kind, period=period, voucher_id=v.id,
                          created_at=V.now_str(), note=note,
                          amount=L.r2(sum(e.get("debit", 0) for e in entries)))
    db.add(rec)
    db.flush()
    return {"record_id": rec.id, "voucher_id": v.id, "voucher_no": v.voucher_no,
            "amount": rec.amount, "kind": kind}


def _month_date(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def _last_amount(db: Session, kind: str, period: str) -> float:
    rec = db.query(CarryoverRecord).filter(
        CarryoverRecord.kind == kind,
        CarryoverRecord.period < period,
        CarryoverRecord.status == "active",
    ).order_by(CarryoverRecord.period.desc()).first()
    return L.r2(rec.amount) if rec else 0.0


def _period_income(db: Session, period: str) -> float:
    """本期营业收入（主营业务收入 + 其他业务收入，贷方为正）"""
    return L.r2(-(L._code_net(db, "5001", to_period=period, from_period=period)
                  + L._code_net(db, "5051", to_period=period, from_period=period)))


def _credit_balance(db: Session, code: str, period: str) -> float:
    """科目截至期末的贷方余额（贷方为正；借方余额返回负数）"""
    ids = L.account_ids_for(db, code, rollup=True)
    return L.r2(-L.signed_balance(db, ids, to_period=period)) if ids else 0.0


# ---------- 结转配置 ----------

STEPS = [
    # (kind, 名称, 默认顺序, 分录说明, 金额来源 manual/auto/last, 是否可手工改金额)
    ("sales_cost", "结转销售成本", 10, "借：主营业务成本　贷：库存商品", "manual", True),
    ("salary", "计提工资", 20, "借：管理费用-工资　贷：应付职工薪酬", "manual", True),
    ("pay_salary", "发放工资", 25, "借：应付职工薪酬　贷：银行存款（+代扣个税）", "auto", True),
    ("pay_bonus", "发放全年一次性奖金", 30, "借：应付职工薪酬　贷：银行存款（+代扣个税）", "manual", True),
    ("depreciation", "计提折旧", 40, "借：管理费用-折旧费　贷：累计折旧", "auto", False),
    ("amortization", "摊销无形资产", 50, "借：管理费用-摊销费　贷：累计摊销", "auto", False),
    ("amortize_deferred", "摊销待摊费用", 60, "借：管理费用-摊销费　贷：长期待摊费用", "manual", True),
    ("vat_free", "免交增值税", 70, "借：应交增值税　贷：营业外收入", "auto", True),
    ("accrue_bonus", "计提全年一次性奖金", 80, "借：管理费用-工资　贷：应付职工薪酬", "manual", True),
    ("accrue_labor", "计提劳务报酬", 90, "借：管理费用-劳务费　贷：其他应付款-劳务报酬", "manual", True),
    ("pay_labor", "发放劳务报酬", 100, "借：其他应付款-劳务报酬　贷：银行存款（+代扣个税）", "auto", True),
    ("tax", "计提税金", 110, "借：税金及附加　贷：应交城建税/教育费附加/地方教育附加", "auto", True),
    ("water_fund", "地方水利基金", 120, "借：税金及附加　贷：应交地方水利建设基金", "auto", True),
    ("stamp_tax", "印花税", 130, "借：税金及附加-印花税　贷：应交印花税", "manual", True),
    ("union_fee", "工会经费", 140, "借：管理费用-工会经费　贷：应付职工薪酬-工会经费", "auto", True),
    ("income_tax", "计提所得税", 150, "借：所得税费用　贷：应交所得税", "auto", True),
    ("exchange", "结转汇兑损益", 160, "借/贷：外币科目　贷/借：财务费用-汇兑损益", "auto", False),
    ("profit", "结转本期损益", 170, "损益类科目余额转入本年利润", "auto", False),
    ("retain_profit", "结转未分配利润", 180, "借：本年利润　贷：利润分配-未分配利润", "auto", False),
]

STEP_META = {k: {"kind": k, "name": n, "order": o, "desc": d,
                 "amount_mode": m, "manual_amount": bool(man)}
             for k, n, o, d, m, man in STEPS}

KIND_NAMES = {k: n for k, n, _o, _d, _m, _man in STEPS}

DEFAULT_RATES = {
    "city": 0.07, "edu": 0.03, "local_edu": 0.02,
    "income_tax": 0.25, "water_fund": 0.005, "union_fee": 0.02, "stamp_tax": 0.0003,
}

# 各步骤默认科目（可在结转配置中覆盖）
DEFAULT_ACCOUNTS = {
    "sales_cost": {"expense": "5401", "credit": "1405"},
    "salary": {"expense": "560201", "payable": "221101"},
    "pay_salary": {"payable": "221101", "bank": "1002", "tax": "222113"},
    "pay_bonus": {"payable": "221101", "bank": "1002", "tax": "222113"},
    "depreciation": {"expense": "560202", "credit": "1602"},
    "amortization": {"expense": "560203", "credit": "1702"},
    "amortize_deferred": {"expense": "560203", "credit": "1801"},
    "vat_free": {"vat": "222101", "income": "5301"},
    "accrue_bonus": {"expense": "560201", "payable": "221101"},
    "accrue_labor": {"expense": "560212", "payable": "224101"},
    "pay_labor": {"payable": "224101", "bank": "1002", "tax": "222113"},
    "tax": {"city_expense": "540301", "city_payable": "222106",
            "edu_expense": "540302", "edu_payable": "222108",
            "local_edu_expense": "540303", "local_edu_payable": "222109"},
    "water_fund": {"expense": "540310", "payable": "222115"},
    "stamp_tax": {"expense": "540304", "payable": "222114"},
    "union_fee": {"expense": "560213", "payable": "221104"},
    "income_tax": {"expense": "5801", "payable": "222112"},
    "exchange": {"gain_loss": "560304"},
    "profit": {"profit": "3103"},
    "retain_profit": {"profit": "3103", "retained": "3104"},
}

# 自动创建明细科目时的默认科目名
AUTO_ACCOUNT_NAMES = {
    ("vat_free", "income"): ("免征增值税", "C", "income"),
    ("water_fund", "expense"): ("地方水利基金", "D", "expense"),
    ("water_fund", "payable"): ("应交地方水利建设基金", "C", "liability"),
    ("union_fee", "expense"): ("工会经费", "D", "expense"),
    ("union_fee", "payable"): ("工会经费", "C", "liability"),
    ("accrue_labor", "expense"): ("劳务费", "D", "expense"),
    ("accrue_labor", "payable"): ("劳务报酬", "C", "liability"),
    ("pay_labor", "payable"): ("劳务报酬", "C", "liability"),
    ("exchange", "gain_loss"): ("汇兑损益", "D", "expense"),
    ("amortize_deferred", "credit"): ("长期待摊费用", "D", "asset"),
}


def default_config() -> dict:
    steps = {}
    for kind, _n, order, _d, mode, _man in STEPS:
        steps[kind] = {
            "enabled": True, "order": order, "amount_mode": mode,
            "default_amount": 0.0,
            "accounts": dict(DEFAULT_ACCOUNTS.get(kind, {})),
        }
    return {"steps": steps, "rates": dict(DEFAULT_RATES)}


def get_config(db: Session) -> dict:
    """合并配置：默认值 ← 旧版独立设置 ← carryover_config 保存值（后者优先）"""
    cfg = default_config()
    # 兼容旧版独立税率设置
    legacy_rates = {"city": "city_tax_rate", "edu": "edu_rate",
                    "local_edu": "local_edu_rate", "income_tax": "income_tax_rate"}
    for k, skey in legacy_rates.items():
        val = L.get_setting(db, skey, "")
        if val:
            try:
                cfg["rates"][k] = float(val)
            except ValueError:
                pass
    # 兼容旧版独立科目设置
    legacy_accounts = {
        ("sales_cost", "expense"): "sales_cost_expense_account",
        ("sales_cost", "credit"): "sales_cost_credit_account",
        ("salary", "expense"): "salary_expense_account",
        ("salary", "payable"): "payable_salary_account",
        ("depreciation", "expense"): "depreciation_expense_account",
        ("amortization", "expense"): "amortization_expense_account",
        ("vat_free", "vat"): "vat_account",
        ("profit", "profit"): "profit_account",
    }
    for (kind, role), skey in legacy_accounts.items():
        val = L.get_setting(db, skey, "")
        if val:
            cfg["steps"][kind]["accounts"][role] = val
    # 保存的结转配置（优先级最高）
    raw = L.get_setting(db, "carryover_config", "")
    if raw:
        try:
            saved = json.loads(raw)
        except ValueError:
            saved = {}
        for kind, sc in (saved.get("steps") or {}).items():
            if kind not in cfg["steps"] or not isinstance(sc, dict):
                continue
            base = cfg["steps"][kind]
            for key in ("enabled", "order", "amount_mode", "default_amount"):
                if key in sc:
                    base[key] = sc[key]
            if isinstance(sc.get("accounts"), dict):
                base["accounts"].update({k: str(v) for k, v in sc["accounts"].items() if v})
        for k, v in (saved.get("rates") or {}).items():
            if k in cfg["rates"]:
                try:
                    cfg["rates"][k] = float(v)
                except (TypeError, ValueError):
                    pass
    return cfg


def save_config(db: Session, payload: dict) -> dict:
    cfg = get_config(db)
    steps = payload.get("steps") or {}
    for kind, sc in steps.items():
        if kind not in cfg["steps"] or not isinstance(sc, dict):
            raise ValueError(f"未知结转步骤：{kind}")
        base = cfg["steps"][kind]
        if "enabled" in sc:
            base["enabled"] = bool(sc["enabled"])
        if sc.get("order") is not None:
            base["order"] = int(sc["order"])
        if sc.get("amount_mode"):
            if sc["amount_mode"] not in ("manual", "auto", "last"):
                raise ValueError(f"{kind} 金额来源无效：{sc['amount_mode']}")
            base["amount_mode"] = sc["amount_mode"]
        if sc.get("default_amount") is not None:
            amt = float(sc["default_amount"])
            if amt < 0:
                raise ValueError(f"{kind} 默认金额不能为负")
            base["default_amount"] = L.r2(amt)
        if isinstance(sc.get("accounts"), dict):
            for role, code in sc["accounts"].items():
                if code:
                    base["accounts"][role] = str(code)
    for k, v in (payload.get("rates") or {}).items():
        if k not in cfg["rates"]:
            raise ValueError(f"未知税率项：{k}")
        rate = float(v)
        if rate < 0 or rate > 1:
            raise ValueError(f"税率 {k} 必须在 0~1 之间")
        cfg["rates"][k] = rate
    s = db.query(Setting).filter(Setting.key == "carryover_config").first()
    if not s:
        s = Setting(key="carryover_config")
        db.add(s)
    s.value = json.dumps(cfg, ensure_ascii=False)
    return cfg


# ---------- 各步骤金额测算（plan） ----------
# plan_* 返回 dict：
#   {"lines": [{"code","name","summary","debit","credit"}...], "amount": 借方合计,
#    "note": 备注, "skip": 跳过原因(可选), "info": 预览信息(可选)}

def _line(code: str, name: str, summary: str, debit: float = 0.0, credit: float = 0.0):
    return {"code": code, "name": name, "summary": summary,
            "debit": L.r2(debit), "credit": L.r2(credit)}


def _manual_amount(db, kind: str, period: str, amount, cfg) -> float:
    """手工金额解析：入参 > 配置默认 > 上期结转额"""
    if amount is not None:
        return L.r2(amount)
    dflt = float(cfg["steps"][kind].get("default_amount") or 0)
    if dflt:
        return L.r2(dflt)
    return _last_amount(db, kind, period)


def plan_sales_cost(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["sales_cost"]["accounts"]
    amt = _manual_amount(db, "sales_cost", period, amount, cfg)
    if amt <= 0:
        return {"lines": [], "amount": 0.0,
                "skip": "结转金额为 0（可在结转配置中设置默认金额或手工录入）",
                "info": {"expense_code": accs["expense"], "credit_code": accs["credit"],
                         "period_income": _period_income(db, period),
                         "suggested_amount": _last_amount(db, "sales_cost", period)}}
    s = "结转本月销售成本"
    return {"amount": amt, "note": s, "info": {
        "expense_code": accs["expense"], "credit_code": accs["credit"],
        "period_income": _period_income(db, period),
        "suggested_amount": _last_amount(db, "sales_cost", period)},
        "lines": [_line(accs["expense"], "主营业务成本", s, debit=amt),
                  _line(accs["credit"], "库存商品", s, credit=amt)]}


def plan_salary(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["salary"]["accounts"]
    amt = _manual_amount(db, "salary", period, amount, cfg)
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "计提金额为 0",
                "info": {"expense_code": accs["expense"], "payable_code": accs["payable"],
                         "suggested_amount": _last_amount(db, "salary", period)}}
    s = "计提本月职工工资"
    return {"amount": amt, "note": s, "info": {
        "expense_code": accs["expense"], "payable_code": accs["payable"],
        "suggested_amount": _last_amount(db, "salary", period)},
        "lines": [_line(accs["expense"], "工资费用", s, debit=amt),
                  _line(accs["payable"], "应付职工薪酬-工资", s, credit=amt)]}


def _plan_payment(db, kind, period, amount, withheld, cfg):
    """发放类（工资/奖金/劳务报酬）：借 应付，贷 银行 + 代扣个税"""
    cfg = cfg or get_config(db)
    accs = cfg["steps"][kind]["accounts"]
    payable = accs["payable"]
    withheld = L.r2(withheld or 0)
    if withheld < 0:
        raise ValueError("代扣个税不能为负")
    if amount is not None:
        gross = L.r2(amount)
    else:
        gross = _credit_balance(db, payable, period)
        if cfg["steps"][kind].get("amount_mode") == "manual":
            dflt = float(cfg["steps"][kind].get("default_amount") or 0)
            if dflt:
                gross = L.r2(dflt)
        if gross <= 0:
            gross = _last_amount(db, kind, period)
    if gross <= 0:
        return {"lines": [], "amount": 0.0,
                "skip": f"{payable} 无待发放余额且未录入金额",
                "info": {"payable_code": payable, "suggested_amount": gross,
                         "withheld": withheld}}
    if withheld >= gross:
        raise ValueError("代扣个税不能大于等于应发金额")
    name = KIND_NAMES[kind]
    net = L.r2(gross - withheld)
    lines = [_line(payable, "应付职工薪酬", f"{name}", debit=gross)]
    if net > 0:
        lines.append(_line(accs["bank"], "银行存款", f"{name}", credit=net))
    if withheld > 0:
        lines.append(_line(accs["tax"], "应交个人所得税", f"{name}（代扣个税）", credit=withheld))
    return {"amount": gross, "note": name,
            "info": {"payable_code": payable, "suggested_amount": gross, "withheld": withheld},
            "lines": lines}


def plan_pay_salary(db, period, amount=None, withheld=0, cfg=None):
    return _plan_payment(db, "pay_salary", period, amount, withheld, cfg)


def plan_pay_bonus(db, period, amount=None, withheld=0, cfg=None):
    return _plan_payment(db, "pay_bonus", period, amount, withheld, cfg)


def plan_pay_labor(db, period, amount=None, withheld=0, cfg=None):
    return _plan_payment(db, "pay_labor", period, amount, withheld, cfg)


def plan_accrue_bonus(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["accrue_bonus"]["accounts"]
    amt = _manual_amount(db, "accrue_bonus", period, amount, cfg)
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "计提金额为 0",
                "info": {"suggested_amount": _last_amount(db, "accrue_bonus", period)}}
    s = "计提全年一次性奖金"
    return {"amount": amt, "note": s, "info": {
        "suggested_amount": _last_amount(db, "accrue_bonus", period)},
        "lines": [_line(accs["expense"], "工资费用", s, debit=amt),
                  _line(accs["payable"], "应付职工薪酬", s, credit=amt)]}


def plan_accrue_labor(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["accrue_labor"]["accounts"]
    amt = _manual_amount(db, "accrue_labor", period, amount, cfg)
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "计提金额为 0",
                "info": {"suggested_amount": _last_amount(db, "accrue_labor", period)}}
    s = "计提劳务报酬"
    return {"amount": amt, "note": s, "info": {
        "suggested_amount": _last_amount(db, "accrue_labor", period)},
        "lines": [_line(accs["expense"], "劳务费", s, debit=amt),
                  _line(accs["payable"], "其他应付款-劳务报酬", s, credit=amt)]}


def plan_amortize_deferred(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["amortize_deferred"]["accounts"]
    amt = _manual_amount(db, "amortize_deferred", period, amount, cfg)
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "摊销金额为 0",
                "info": {"suggested_amount": _last_amount(db, "amortize_deferred", period)}}
    s = "摊销本月待摊费用"
    return {"amount": amt, "note": s, "info": {
        "suggested_amount": _last_amount(db, "amortize_deferred", period)},
        "lines": [_line(accs["expense"], "摊销费", s, debit=amt),
                  _line(accs["credit"], "长期待摊费用", s, credit=amt)]}


def plan_depreciation(db, period, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["depreciation"]["accounts"]
    items, total = [], 0.0
    for fa in db.query(FixedAsset).filter(FixedAsset.in_use == 1).all():
        amt = L.r2(fa.original_value * (1 - (fa.residual_rate or 0)) / (fa.life_months or 1))
        total = L.r2(total + amt)
        items.append({"id": fa.id, "name": fa.name, "amount": amt,
                      "expense_code": fa.expense_account_code or accs["expense"]})
    if not items:
        return {"lines": [], "amount": 0.0, "skip": "尚未录入固定资产",
                "info": {"items": [], "total": 0.0, "credit_code": accs["credit"],
                         "expense_code": accs["expense"]}}
    s = "计提本月固定资产折旧"
    lines = [_line(it["expense_code"], "折旧费", f"{s}（{it['name']}）", debit=it["amount"])
             for it in items if it["amount"] > 0]
    if not lines:
        return {"lines": [], "amount": 0.0, "skip": "本月折旧金额为 0",
                "info": {"items": items, "total": total, "credit_code": accs["credit"],
                         "expense_code": accs["expense"]}}
    lines.append(_line(accs["credit"], "累计折旧", s, credit=total))
    return {"amount": total, "note": s,
            "info": {"items": items, "total": total, "credit_code": accs["credit"],
                     "expense_code": accs["expense"]},
            "lines": lines}


def plan_amortization(db, period, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["amortization"]["accounts"]
    items, total = [], 0.0
    for ia in db.query(IntangibleAsset).filter(IntangibleAsset.in_use == 1).all():
        amt = L.r2(ia.original_value / (ia.amort_months or 1))
        total = L.r2(total + amt)
        items.append({"id": ia.id, "name": ia.name, "amount": amt,
                      "expense_code": ia.expense_account_code or accs["expense"]})
    if not items:
        return {"lines": [], "amount": 0.0, "skip": "尚未录入无形资产",
                "info": {"items": [], "total": 0.0, "credit_code": accs["credit"],
                         "expense_code": accs["expense"]}}
    s = "摊销本月无形资产"
    lines = [_line(it["expense_code"], "摊销费", f"{s}（{it['name']}）", debit=it["amount"])
             for it in items if it["amount"] > 0]
    if not lines:
        return {"lines": [], "amount": 0.0, "skip": "本月摊销金额为 0",
                "info": {"items": items, "total": total, "credit_code": accs["credit"],
                         "expense_code": accs["expense"]}}
    lines.append(_line(accs["credit"], "累计摊销", s, credit=total))
    return {"amount": total, "note": s,
            "info": {"items": items, "total": total, "credit_code": accs["credit"],
                     "expense_code": accs["expense"]},
            "lines": lines}


def plan_profit(db, period, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["profit"]["accounts"]
    lines, info_lines = [], []
    total_income = total_expense = 0.0
    for a in db.query(Account).filter(Account.is_leaf == 1).all():
        if a.category not in ("income", "expense"):
            continue
        d, c = L._entry_sums(db, [a.id], period=period)
        net = L.r2(d - c)
        if abs(net) < 0.005:
            continue
        # 结平方向按余额方向（允许费用科目贷方余额如利息收入/汇兑损益）
        if net > 0:
            lines.append(_line(a.code, a.name, "结转本期损益", credit=net))
        else:
            lines.append(_line(a.code, a.name, "结转本期损益", debit=L.r2(-net)))
        info_lines.append({"account_code": a.code, "account_name": a.name,
                           "direction": "income" if a.category == "income" else "expense",
                           "amount": abs(net)})
        if a.category == "income":
            total_income = L.r2(total_income - net)
        else:
            total_expense = L.r2(total_expense + net)
    info = {"lines": info_lines,
            "total_income": total_income, "total_expense": total_expense,
            "net_profit": L.r2(total_income - total_expense),
            "profit_code": accs["profit"]}
    if not lines:
        return {"lines": [], "amount": 0.0, "skip": "本期没有需要结转的损益科目发生额",
                "info": info}
    net = L.r2(total_income - total_expense)
    if net > 0:
        lines.append(_line(accs["profit"], "本年利润", "结转本期损益", credit=net))
    elif net < 0:
        lines.append(_line(accs["profit"], "本年利润", "结转本期损益", debit=L.r2(-net)))
    return {"amount": L.r2(sum(l["debit"] for l in lines)),
            "note": f"结转本期损益，净额 {net:.2f}",
            "info": info, "lines": lines}


def plan_tax(db, period, vat_base=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["tax"]["accounts"]
    rates = cfg["rates"]
    base = L.r2(vat_base) if vat_base is not None else L.r2(
        -L._code_net(db, L.get_setting(db, "vat_account", "222101"),
                     to_period=period, from_period=period))
    info = {"vat_base": base,
            "city_tax": L.r2(max(base, 0) * rates["city"]),
            "edu_tax": L.r2(max(base, 0) * rates["edu"]),
            "local_edu_tax": L.r2(max(base, 0) * rates["local_edu"]),
            "rates": {"city": rates["city"], "edu": rates["edu"],
                      "local_edu": rates["local_edu"]}}
    if base <= 0:
        return {"lines": [], "amount": 0.0,
                "skip": "计税基数（本期应交增值税）不大于 0", "info": info}
    items = [(accs["city_expense"], accs["city_payable"], info["city_tax"], "城市维护建设税"),
             (accs["edu_expense"], accs["edu_payable"], info["edu_tax"], "教育费附加"),
             (accs["local_edu_expense"], accs["local_edu_payable"],
              info["local_edu_tax"], "地方教育附加")]
    lines, total = [], 0.0
    for exp_code, liab_code, amt, name in items:
        if amt <= 0:
            continue
        lines.append(_line(exp_code, name, f"计提本月税金——{name}", debit=amt))
        lines.append(_line(liab_code, f"应交{name}", f"计提本月税金——{name}", credit=amt))
        total = L.r2(total + amt)
    if not lines:
        return {"lines": [], "amount": 0.0, "skip": "税金金额为 0", "info": info}
    return {"amount": total, "note": f"计税基数 {base:.2f}，合计 {total:.2f}",
            "info": info, "lines": lines}


def plan_water_fund(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["water_fund"]["accounts"]
    base = _period_income(db, period)
    if amount is not None:
        amt = L.r2(amount)
    else:
        dflt = float(cfg["steps"]["water_fund"].get("default_amount") or 0)
        amt = L.r2(dflt) if dflt else L.r2(base * cfg["rates"]["water_fund"])
    info = {"base": base, "rate": cfg["rates"]["water_fund"],
            "suggested_amount": L.r2(base * cfg["rates"]["water_fund"])}
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "地方水利基金金额为 0", "info": info}
    s = "计提地方水利建设基金"
    return {"amount": amt, "note": s, "info": info,
            "lines": [_line(accs["expense"], "地方水利基金", s, debit=amt),
                      _line(accs["payable"], "应交地方水利建设基金", s, credit=amt)]}


def plan_stamp_tax(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["stamp_tax"]["accounts"]
    base = _period_income(db, period)
    suggested = L.r2(base * cfg["rates"]["stamp_tax"])
    if amount is not None:
        amt = L.r2(amount)
    else:
        dflt = float(cfg["steps"]["stamp_tax"].get("default_amount") or 0)
        amt = L.r2(dflt) if dflt else suggested
    info = {"base": base, "rate": cfg["rates"]["stamp_tax"], "suggested_amount": suggested}
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "印花税金额为 0", "info": info}
    s = "计提印花税"
    return {"amount": amt, "note": s, "info": info,
            "lines": [_line(accs["expense"], "印花税", s, debit=amt),
                      _line(accs["payable"], "应交印花税", s, credit=amt)]}


def plan_union_fee(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["union_fee"]["accounts"]
    salary_code = cfg["steps"]["salary"]["accounts"]["payable"]
    ids = L.account_ids_for(db, salary_code, rollup=True)
    d, c = (L._entry_sums(db, ids, period=period) if ids else (0.0, 0.0))
    base = L.r2(c)  # 本期工资计提额
    suggested = L.r2(base * cfg["rates"]["union_fee"])
    if amount is not None:
        amt = L.r2(amount)
    else:
        dflt = float(cfg["steps"]["union_fee"].get("default_amount") or 0)
        amt = L.r2(dflt) if dflt else suggested
    info = {"base": base, "rate": cfg["rates"]["union_fee"], "suggested_amount": suggested}
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "工会经费金额为 0（本期工资计提额为 0）",
                "info": info}
    s = "计提工会经费"
    return {"amount": amt, "note": s, "info": info,
            "lines": [_line(accs["expense"], "工会经费", s, debit=amt),
                      _line(accs["payable"], "应付职工薪酬-工会经费", s, credit=amt)]}


def plan_income_tax(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["income_tax"]["accounts"]
    comps = L.pl_components(db, f"{period[:4]}-01", period, exclude_kind="profit")
    total_profit = L.r2(comps["revenue"] - comps["cost"] - comps["tax_surcharge"]
                        - comps["selling"] - comps["admin"] - comps["finance"]
                        + comps["invest_income"] + comps["nonop_income"]
                        - comps["nonop_expense"])
    accrued = L.r2(L._code_net(db, "5801", to_period=period,
                               from_period=f"{period[:4]}-01", exclude_kind="profit"))
    rate = cfg["rates"]["income_tax"]
    should = L.r2(max(total_profit, 0) * rate)
    info = {"total_profit_ytd": total_profit, "accrued_ytd": accrued, "rate": rate,
            "should_accrue": should, "amount": L.r2(max(should - accrued, 0))}
    amt = L.r2(amount) if amount is not None else info["amount"]
    if amt <= 0:
        return {"lines": [], "amount": 0.0,
                "skip": "本期无需计提所得税（累计应计提 ≤ 已计提）", "info": info}
    s = "计提本月所得税费用"
    return {"amount": amt,
            "note": f"累计利润 {total_profit:.2f}，税率 {rate}", "info": info,
            "lines": [_line(accs["expense"], "所得税费用", s, debit=amt),
                      _line(accs["payable"], "应交所得税", s, credit=amt)]}


def plan_vat_free(db, period, amount=None, cfg=None):
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["vat_free"]["accounts"]
    taxpayer = L.get_setting(db, "taxpayer_type", "small")
    basis = L.get_setting(db, "vat_free_basis", "month")
    month_limit = float(L.get_setting(db, "vat_free_month_limit", "100000"))
    quarter_limit = float(L.get_setting(db, "vat_free_quarter_limit", "300000"))
    sales_month = _period_income(db, period)
    q = (int(period[5:7]) - 1) // 3 + 1
    from_q = f"{period[:4]}-{(q - 1) * 3 + 1:02d}"
    sales_quarter = L.r2(-L._code_net(db, "5001", to_period=period, from_period=from_q)
                         - L._code_net(db, "5051", to_period=period, from_period=from_q))
    vat_amt = L.r2(-L._code_net(db, L.get_setting(db, "vat_account", "222101"),
                                to_period=period, from_period=period))
    ok_month = sales_month <= month_limit
    ok_quarter = sales_quarter <= quarter_limit
    eligible = taxpayer == "small" and (ok_month if basis == "month" else ok_quarter)
    info = {
        "taxpayer_type": taxpayer, "basis": basis,
        "sales_month": sales_month, "sales_quarter": sales_quarter,
        "month_limit": month_limit, "quarter_limit": quarter_limit,
        "ok_month": ok_month, "ok_quarter": ok_quarter, "eligible": eligible,
        "vat_amount": vat_amt, "vat_code": accs["vat"], "income_code": accs["income"],
    }
    if taxpayer != "small":
        return {"lines": [], "amount": 0.0, "skip": "当前为一般纳税人，不适用小规模免征增值税处理",
                "info": info}
    if not eligible:
        return {"lines": [], "amount": 0.0,
                "skip": (f"本期销售额未达免征条件（口径：{'按月' if basis == 'month' else '按季'}）："
                         f"本月销售额 {sales_month:.2f}（限额 {month_limit:.2f}），"
                         f"本季销售额 {sales_quarter:.2f}（限额 {quarter_limit:.2f}）"),
                "info": info}
    amt = L.r2(amount) if amount is not None else vat_amt
    if amt <= 0:
        return {"lines": [], "amount": 0.0, "skip": "本期应交增值税 ≤ 0，无可免交金额", "info": info}
    s = "小规模纳税人免征增值税"
    return {"amount": amt, "note": f"免征增值税 {amt:.2f} 转入营业外收入", "info": info,
            "lines": [_line(accs["vat"], "应交增值税", s, debit=amt),
                      _line(accs["income"], "营业外收入", s, credit=amt)]}


def plan_exchange(db, period, cfg=None):
    """结转汇兑损益：按期末汇率对外币分录重估，差额计入财务费用-汇兑损益

    口径：取本年（锚定年度）以来币种非人民币的分录，按分录汇率折算原币余额，
    与账面本位币余额比较，差额 = 原币余额 × 期末汇率 − 账面本位币余额。
    生成的汇兑损益凭证固定以 CNY 记账，重复执行不会重复调整。
    """
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["exchange"]["accounts"]
    anchor = L.opening_anchor_year(db, period)
    rows = db.query(VoucherEntry, Voucher).join(
        Voucher, Voucher.id == VoucherEntry.voucher_id).filter(
        Voucher.status == "posted", VoucherEntry.currency != "CNY",
        Voucher.period >= f"{anchor}-01", Voucher.period <= period).all()
    per_acc = {}
    for e, v in rows:
        cur = db.query(Currency).filter(Currency.code == e.currency).first()
        if not cur or not cur.rate:
            continue
        agg = per_acc.setdefault(e.account_id, {"orig": 0.0, "rate": cur.rate})
        rate = e.exchange_rate or 1
        agg["orig"] = L.r2(agg["orig"] + (e.debit - e.credit) / rate)
    diffs = []
    for aid, agg in per_acc.items():
        a = db.query(Account).get(aid)
        if not a:
            continue
        # 原币余额 = 期初数量 + 外币分录折算；本位币余额 = 全部账面余额（含期初与已调整额）
        ob = db.query(OpeningBalance).filter(
            OpeningBalance.account_id == aid, OpeningBalance.year == anchor).first()
        orig = L.r2(agg["orig"] + (ob.quantity if ob else 0))
        if abs(orig) < 0.005:
            continue
        cny = L.signed_balance(db, [aid], to_period=period)
        diff = L.r2(orig * agg["rate"] - cny)
        if abs(diff) >= 0.01:
            diffs.append({"code": a.code, "name": a.name, "original": orig,
                          "rate": agg["rate"], "cny_book": cny, "diff": diff})
    diffs.sort(key=lambda d: d["code"])
    info = {"items": diffs}
    if not diffs:
        return {"lines": [], "amount": 0.0, "skip": "无外币业务或无需调整汇兑损益", "info": info}
    s = "结转本期汇兑损益"
    lines, total = [], 0.0
    for d in diffs:
        diff = d["diff"]
        total = L.r2(total + abs(diff))
        if diff > 0:
            lines.append(_line(d["code"], d["name"], s, debit=diff))
            lines.append(_line(accs["gain_loss"], "汇兑损益", s, credit=diff))
        else:
            lines.append(_line(accs["gain_loss"], "汇兑损益", s, debit=L.r2(-diff)))
            lines.append(_line(d["code"], d["name"], s, credit=L.r2(-diff)))
    return {"amount": total, "note": s, "info": info, "lines": lines}


def plan_retain_profit(db, period, cfg=None):
    """结转未分配利润：本年利润余额转入利润分配"""
    cfg = cfg or get_config(db)
    accs = cfg["steps"]["retain_profit"]["accounts"]
    bal = _credit_balance(db, accs["profit"], period)  # 贷方为正
    info = {"profit_balance": bal}
    if abs(bal) < 0.005:
        return {"lines": [], "amount": 0.0, "skip": "本年利润余额为 0，无需结转", "info": info}
    s = "结转本年利润至未分配利润"
    if bal > 0:
        return {"amount": bal, "note": s, "info": info,
                "lines": [_line(accs["profit"], "本年利润", s, debit=bal),
                          _line(accs["retained"], "利润分配-未分配利润", s, credit=bal)]}
    amt = L.r2(-bal)
    return {"amount": amt, "note": s, "info": info,
            "lines": [_line(accs["retained"], "利润分配-未分配利润", s, debit=amt),
                      _line(accs["profit"], "本年利润", s, credit=amt)]}


PLANNERS = {
    "sales_cost": plan_sales_cost, "salary": plan_salary,
    "pay_salary": plan_pay_salary, "pay_bonus": plan_pay_bonus,
    "pay_labor": plan_pay_labor,
    "accrue_bonus": plan_accrue_bonus, "accrue_labor": plan_accrue_labor,
    "amortize_deferred": plan_amortize_deferred,
    "depreciation": plan_depreciation, "amortization": plan_amortization,
    "vat_free": plan_vat_free, "tax": plan_tax, "water_fund": plan_water_fund,
    "stamp_tax": plan_stamp_tax, "union_fee": plan_union_fee,
    "income_tax": plan_income_tax, "exchange": plan_exchange,
    "profit": plan_profit, "retain_profit": plan_retain_profit,
}


def plan(kind: str, db: Session, period: str, amount=None, extra: dict = None):
    fn = PLANNERS.get(kind)
    if not fn:
        raise ValueError(f"未知结转类型：{kind}")
    extra = extra or {}
    kwargs = {}
    if kind in ("pay_salary", "pay_bonus", "pay_labor"):
        kwargs["withheld"] = extra.get("withheld")
    if kind == "tax" and extra.get("vat_base") is not None:
        kwargs["vat_base"] = extra.get("vat_base")
    if fn in (plan_sales_cost, plan_salary, plan_accrue_bonus, plan_accrue_labor,
              plan_amortize_deferred, plan_water_fund, plan_stamp_tax, plan_union_fee,
              plan_income_tax, plan_vat_free) or kind in ("pay_salary", "pay_bonus", "pay_labor"):
        return fn(db, period, amount=amount, **kwargs)
    return fn(db, period, **kwargs)


# ---------- 预览（兼容旧接口返回字段） ----------

def preview(kind: str, db: Session, period: str, extra: dict = None) -> dict:
    p = plan(kind, db, period, amount=None, extra=extra)
    out = dict(p.get("info") or {})
    out["lines_preview"] = p.get("lines") or []
    out["amount"] = p.get("amount", 0.0)
    if p.get("skip"):
        out["skip"] = p["skip"]
    return out


def preview_sales_cost(db, period):
    return preview("sales_cost", db, period)


def preview_salary(db, period):
    return preview("salary", db, period)


def preview_depreciation(db, period):
    return preview("depreciation", db, period)


def preview_amortization(db, period):
    return preview("amortization", db, period)


def preview_profit(db, period):
    return preview("profit", db, period)


def preview_tax(db, period):
    return preview("tax", db, period)


def preview_income_tax(db, period):
    return preview("income_tax", db, period)


def preview_vat_free(db, period):
    return preview("vat_free", db, period)


# ---------- 执行 ----------

def _category_of(code: str, credit: bool) -> str:
    if code[:1] == "1":
        return "asset"
    if code[:1] == "2":
        return "liability"
    if code[:1] == "3":
        return "equity"
    if code[:1] == "5":
        # 损益类：收入科目家族才是 income（如 5001/5051/5111/5301）
        return "income" if code.startswith(("5001", "5051", "5111", "5301")) else "expense"
    return "income" if credit else "expense"


def execute(kind: str, db: Session, period: str, amount=None, extra: dict = None,
            summary: str = None) -> dict:
    if not L.valid_period(period):
        raise ValueError(f"期间格式错误：{period}")
    if V.is_period_closed(db, period):
        raise ValueError(f"会计期间 {period} 已结账，不能执行结转")
    p = plan(kind, db, period, amount=amount, extra=extra)
    if p.get("skip"):
        raise ValueError(p["skip"])
    entries = []
    for ln in p["lines"]:
        acc = resolve_account(db, ln["code"], name=ln.get("name"),
                              direction="C" if ln.get("credit") else "D",
                              category=_category_of(ln["code"], bool(ln.get("credit"))))
        e = {"account_id": acc.id, "summary": summary or ln.get("summary") or "",
             "debit": ln["debit"], "credit": ln["credit"]}
        if kind == "exchange":
            e["currency"] = "CNY"
            e["exchange_rate"] = 1
        entries.append(e)
    return _mk(db, kind, period, _month_date(period), entries,
               summary or p.get("note") or KIND_NAMES.get(kind, kind))


def do_sales_cost(db, period, amount: float, summary: str = "结转本月销售成本"):
    return execute("sales_cost", db, period, amount=amount, summary=summary)


def do_salary(db, period, amount: float, expense_code: str = None,
              summary: str = "计提本月职工工资"):
    if expense_code:
        cfg = get_config(db)
        cfg["steps"]["salary"]["accounts"]["expense"] = expense_code
        p = plan("salary", db, period, amount=amount)
        if p.get("skip"):
            raise ValueError(p["skip"])
        entries = [{"account_id": resolve_account(db, expense_code, name="工资费用").id,
                    "summary": summary, "debit": p["amount"]},
                   {"account_id": _acc(db, cfg["steps"]["salary"]["accounts"]["payable"]).id,
                    "summary": summary, "credit": p["amount"]}]
        return _mk(db, "salary", period, _month_date(period), entries, summary)
    return execute("salary", db, period, amount=amount, summary=summary)


def do_depreciation(db, period, summary: str = "计提本月固定资产折旧"):
    return execute("depreciation", db, period, summary=summary)


def do_amortization(db, period, summary: str = "摊销本月无形资产"):
    return execute("amortization", db, period, summary=summary)


def do_profit(db, period, summary: str = "结转本期损益"):
    return execute("profit", db, period, summary=summary)


def do_tax(db, period, vat_base: float = None, summary: str = "计提本月税金"):
    return execute("tax", db, period,
                   extra={"vat_base": vat_base} if vat_base is not None else None,
                   summary=summary)


def do_income_tax(db, period, amount: float = None, summary: str = "计提本月所得税费用"):
    return execute("income_tax", db, period, amount=amount, summary=summary)


def do_vat_free(db, period, amount: float = None, summary: str = "小规模纳税人免征增值税"):
    return execute("vat_free", db, period, amount=amount, summary=summary)


def run_all(db: Session, period: str, kinds: list = None, amounts: dict = None,
            config: dict = None, stop_on_error: bool = False) -> dict:
    """一键结转：按配置顺序执行启用的结转步骤。

    - 金额为 0 / 不适用的步骤自动跳过并说明原因。
    - 单步失败默认记录并继续（stop_on_error=True 时中断）。
    """
    if not L.valid_period(period):
        raise ValueError(f"期间格式错误：{period}")
    if V.is_period_closed(db, period):
        raise ValueError(f"会计期间 {period} 已结账，不能执行结转")
    cfg = config or get_config(db)
    amounts = amounts or {}
    steps = sorted(cfg["steps"].items(), key=lambda kv: (kv[1].get("order", 0), kv[0]))
    results = []
    for kind, sc in steps:
        if kinds is not None and kind not in kinds:
            continue
        if kinds is None and not sc.get("enabled", True):
            results.append({"kind": kind, "name": KIND_NAMES.get(kind, kind),
                            "status": "disabled", "message": "已在结转配置中停用"})
            continue
        try:
            amt = amounts.get(kind)
            p = plan(kind, db, period, amount=float(amt) if amt not in (None, "") else None)
            if p.get("skip"):
                results.append({"kind": kind, "name": KIND_NAMES.get(kind, kind),
                                "status": "skipped", "message": p["skip"], "amount": 0.0})
                continue
            r = execute(kind, db, period,
                        amount=float(amt) if amt not in (None, "") else None)
            results.append({"kind": kind, "name": KIND_NAMES.get(kind, kind),
                            "status": "created", "amount": r["amount"],
                            "voucher_no": r["voucher_no"], "voucher_id": r["voucher_id"],
                            "message": r.get("note", "")})
        except ValueError as e:
            results.append({"kind": kind, "name": KIND_NAMES.get(kind, kind),
                            "status": "failed", "message": str(e), "amount": 0.0})
            if stop_on_error:
                break
    created = [r for r in results if r["status"] == "created"]
    return {"period": period, "results": results,
            "created_count": len(created),
            "total_amount": L.r2(sum(r["amount"] for r in created))}


# ---------- 结转记录 / 反结转 ----------

def list_records(db: Session, period: str = None, from_period: str = None,
                 to_period: str = None, year: str = None):
    q = db.query(CarryoverRecord).order_by(CarryoverRecord.period.desc(), CarryoverRecord.id.desc())
    if period:
        q = q.filter(CarryoverRecord.period == period)
    else:
        if year:
            q = q.filter(CarryoverRecord.period >= f"{year}-01",
                         CarryoverRecord.period <= f"{year}-12")
        else:
            if from_period:
                q = q.filter(CarryoverRecord.period >= from_period)
            if to_period:
                q = q.filter(CarryoverRecord.period <= to_period)
    out = []
    for r in q.all():
        v = db.query(Voucher).get(r.voucher_id)
        out.append({
            "id": r.id, "kind": r.kind,
            "kind_name": KIND_NAMES.get(r.kind, r.kind),
            "period": r.period, "amount": r.amount,
            "status": r.status, "created_at": r.created_at, "note": r.note,
            "voucher_id": r.voucher_id, "voucher_no": v.voucher_no if v else "",
        })
    return out


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
    tb = L.trial_balance(db, period=period)
    if not tb["balanced"]:
        bad = [f"{r['code']} {r['name']}" for r in tb["rows"]
               if (r["closing_debit"] or r["closing_credit"])
               and not r.get("is_leaf", True)]
        hint = f"（非末级科目直接记账：{'、'.join(bad[:3])}）" if bad else ""
        raise ValueError(
            f"试算不平衡：借方合计 {tb['total_debit']:.2f} ≠ 贷方合计 "
            f"{tb['total_credit']:.2f}，差额 {tb['difference']:.2f}，不能结账{hint}")
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
