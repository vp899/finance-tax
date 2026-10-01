"""凭证服务：编号、校验、现金流量自动对照"""
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Account, Voucher, VoucherEntry, AccountCashflowMap, Period
from . import ledger as L

CASH_CODES = ("1001", "1002", "1012")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_period_closed(db: Session, period: str) -> bool:
    p = db.query(Period).filter(Period.period == period).first()
    return bool(p and p.status == "closed")


def ensure_period(db: Session, period: str):
    p = db.query(Period).filter(Period.period == period).first()
    if not p:
        p = Period(period=period, status="open")
        db.add(p)
        db.flush()
    return p


def next_voucher_no(db: Session, period: str, vtype: str) -> str:
    prefix = vtype or "记"
    key = f"{prefix}-{period.replace('-', '')}-"
    rows = db.query(Voucher.voucher_no).filter(
        Voucher.voucher_no.like(f"{key}%")).all()
    max_seq = 0
    for (no,) in rows:
        try:
            max_seq = max(max_seq, int(no[len(key):]))
        except ValueError:
            pass
    return f"{key}{max_seq + 1:03d}"


def is_cash_account(acc: Account) -> bool:
    return acc.code in CASH_CODES or (
        acc.code.startswith(("1001", "1002", "1012")) and acc.code[:4] in CASH_CODES
    )


def find_cashflow_code(db: Session, acc: Account) -> str:
    """按科目自身→上级逐级回退查现金流量对照"""
    code = acc.code
    while code:
        a = account_map_by_code(db, code)
        if a:
            m = db.query(AccountCashflowMap).filter(
                AccountCashflowMap.account_id == a.id).first()
            if m:
                return m.cashflow_code
        code = code[:-1]
    return None


def account_map_by_code(db: Session, code: str):
    return db.query(Account).filter(Account.code == code).first()


def auto_cashflow(db: Session, entries_data: list, account_map: dict):
    """为现金科目的分录自动补现金流量项目（按金额最大的对方科目对照）"""
    contra = []  # (amount, account)
    for e in entries_data:
        acc = account_map.get(e.get("account_id"))
        if acc and not is_cash_account(acc):
            amt = abs(L.r2(e.get("debit", 0)) - L.r2(e.get("credit", 0)))
            contra.append((amt, acc))
    contra.sort(key=lambda t: -t[0])
    for e in entries_data:
        acc = account_map.get(e.get("account_id"))
        if acc and is_cash_account(acc) and not e.get("cashflow_code"):
            code = None
            for _amt, cacc in contra:
                code = find_cashflow_code(db, cacc)
                if code:
                    break
            e["cashflow_code"] = code or ("204" if e.get("credit", 0) > 0 else "103")
    return entries_data


def validate_entries(db: Session, entries_data: list):
    """校验分录合法性，返回 (account_map, 错误列表)"""
    errors = []
    if not entries_data:
        return {}, ["凭证至少需要一行分录"]
    ids = [e.get("account_id") for e in entries_data if e.get("account_id")]
    accounts = db.query(Account).filter(Account.id.in_(ids)).all() if ids else []
    amap = {a.id: a for a in accounts}
    total_d = total_c = 0.0
    for i, e in enumerate(entries_data, 1):
        acc = amap.get(e.get("account_id"))
        if not acc:
            errors.append(f"第{i}行：科目不存在")
            continue
        if not acc.is_leaf:
            errors.append(f"第{i}行：科目 {acc.code} {acc.name} 不是末级科目，不能记账")
        d_raw = float(e.get("debit", 0) or 0)
        c_raw = float(e.get("credit", 0) or 0)
        if abs(d_raw - round(d_raw, 2)) > 1e-9 or abs(c_raw - round(c_raw, 2)) > 1e-9:
            errors.append(f"第{i}行：金额最多两位小数")
        d = L.r2(d_raw)
        c = L.r2(c_raw)
        if d < 0 or c < 0:
            errors.append(f"第{i}行：金额不能为负（红字冲销请用负数以外的方式）")
        if d > 0 and c > 0:
            errors.append(f"第{i}行：借方与贷方金额不能同时有值")
        if d == 0 and c == 0:
            errors.append(f"第{i}行：借贷方金额不能同时为零")
        if abs(d - L.r2(d)) > 1e-9 or abs(c - L.r2(c)) > 1e-9:
            errors.append(f"第{i}行：金额最多两位小数")
        total_d, total_c = L.r2(total_d + d), L.r2(total_c + c)
    if abs(total_d - total_c) >= 0.005:
        errors.append(f"借贷不平衡：借方合计 {total_d:.2f}，贷方合计 {total_c:.2f}")
    return amap, errors


def build_entries(voucher: Voucher, entries_data: list, account_map: dict):
    voucher.entries.clear()
    for i, e in enumerate(entries_data, 1):
        acc = account_map[e["account_id"]]
        voucher.entries.append(VoucherEntry(
            line_no=i,
            account_id=acc.id,
            summary=(e.get("summary") or "")[:200],
            debit=L.r2(e.get("debit", 0) or 0),
            credit=L.r2(e.get("credit", 0) or 0),
            currency=e.get("currency") or acc.currency or "CNY",
            exchange_rate=L.r2(e.get("exchange_rate", 1) or 1),
            quantity=e.get("quantity") or 0,
            unit=e.get("unit") or "",
            cashflow_code=e.get("cashflow_code") or None,
        ))


def create_voucher(db: Session, *, date: str, vtype: str = "记", entries: list,
                   status: str = "posted", source: str = "manual",
                   carryover_kind: str = None, remark: str = "",
                   voucher_no: str = None) -> Voucher:
    period = date[:7]
    if not L.valid_period(period):
        raise ValueError(f"日期无效：{date}")
    if is_period_closed(db, period):
        raise ValueError(f"会计期间 {period} 已结账，不能新增凭证")
    amap, errors = validate_entries(db, entries)
    if errors:
        raise ValueError("；".join(errors))
    entries = auto_cashflow(db, entries, amap)
    ensure_period(db, period)
    v = Voucher(
        voucher_no=voucher_no or next_voucher_no(db, period, vtype),
        vtype=vtype or "记", date=date, period=period, status=status,
        source=source, carryover_kind=carryover_kind,
        created_at=now_str(), posted_at=now_str() if status == "posted" else "",
        remark=remark[:200],
    )
    db.add(v)
    db.flush()
    build_entries(v, entries, amap)
    return v
