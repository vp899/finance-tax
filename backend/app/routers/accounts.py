"""科目管理 + 期初余额"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Account, OpeningBalance, VoucherEntry
from ..services import ledger as L

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("")
def list_accounts(db: Session = Depends(get_db)):
    rows = []
    for a in db.query(Account).order_by(Account.code).all():
        rows.append({
            "id": a.id, "code": a.code, "name": a.name, "parent_code": a.parent_code,
            "direction": a.direction, "category": a.category, "pinyin": a.pinyin,
            "is_leaf": bool(a.is_leaf), "level": a.level, "currency": a.currency,
            "unit": a.unit, "cashflow_code": a.cashflow_code, "remark": a.remark,
        })
    return rows


@router.get("/suggest")
def suggest(q: str = "", db: Session = Depends(get_db)):
    """智能补全：按编码/名称/拼音匹配科目，附带当前余额"""
    q = (q or "").strip().lower()
    query = db.query(Account)
    if q:
        query = query.filter(
            (Account.code.like(f"{q}%")) |
            (Account.name.like(f"%{q}%")) |
            (Account.pinyin.like(f"%{q}%"))
        )
    accs = query.order_by(Account.code).limit(30).all()
    out = []
    for a in accs:
        bal = L.all_time_balance(db, [a.id])
        out.append({
            "id": a.id, "code": a.code, "name": a.name,
            "is_leaf": bool(a.is_leaf), "direction": a.direction,
            "balance": bal, "text": f"{a.code} {a.name}",
        })
    return out


@router.post("")
def create_account(body: dict, db: Session = Depends(get_db)):
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "科目编码和名称必填")
    if db.query(Account).filter(Account.code == code).first():
        raise HTTPException(400, f"科目编码已存在：{code}")
    parent_code = (body.get("parent_code") or "").strip() or None
    level = 1
    if parent_code:
        parent = L.account_by_code(db, parent_code)
        if not parent:
            raise HTTPException(400, f"上级科目不存在：{parent_code}")
        parent.is_leaf = 0
        level = parent.level + 1
    a = Account(
        code=code, name=name, parent_code=parent_code,
        direction=body.get("direction") or "D",
        category=body.get("category") or "asset",
        pinyin=(body.get("pinyin") or "").strip(),
        is_leaf=1, level=level,
        currency=body.get("currency") or "CNY",
        unit=body.get("unit") or "",
        cashflow_code=body.get("cashflow_code") or None,
        remark=body.get("remark") or "",
    )
    db.add(a)
    db.commit()
    return {"id": a.id, "code": a.code, "name": a.name}


@router.put("/{account_id}")
def update_account(account_id: int, body: dict, db: Session = Depends(get_db)):
    a = db.query(Account).get(account_id)
    if not a:
        raise HTTPException(404, "科目不存在")
    for field in ("name", "pinyin", "direction", "category", "currency", "unit", "remark"):
        if field in body:
            setattr(a, field, body[field])
    if "cashflow_code" in body:
        a.cashflow_code = body["cashflow_code"] or None
    db.commit()
    return {"ok": True}


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    a = db.query(Account).get(account_id)
    if not a:
        raise HTTPException(404, "科目不存在")
    used = db.query(VoucherEntry).filter(VoucherEntry.account_id == account_id).count()
    if used:
        raise HTTPException(400, f"科目 {a.code} 已有 {used} 条分录，不能删除")
    if db.query(Account).filter(Account.parent_code == a.code).count():
        raise HTTPException(400, f"科目 {a.code} 存在下级科目，不能删除")
    ob = db.query(OpeningBalance).filter(
        OpeningBalance.account_id == account_id,
        ((OpeningBalance.debit != 0) | (OpeningBalance.credit != 0) |
         (OpeningBalance.quantity != 0))).count()
    if ob:
        raise HTTPException(400, f"科目 {a.code} 已有期初余额，请先在科目期初中清零后再删除，"
                                f"否则会导致试算不平衡")
    # 清理零值期初行，避免外键残留
    db.query(OpeningBalance).filter(OpeningBalance.account_id == account_id).delete()
    parent = L.account_by_code(db, a.parent_code) if a.parent_code else None
    db.delete(a)
    db.flush()
    if parent and not db.query(Account).filter(Account.parent_code == parent.code).count():
        parent.is_leaf = 1
    db.commit()
    return {"ok": True}


@router.get("/openings/list")
def list_openings(year: str, db: Session = Depends(get_db)):
    obs = {o.account_id: o for o in db.query(OpeningBalance).filter(OpeningBalance.year == year).all()}
    rows = []
    td = tc = 0.0
    # 末级科目 + 历史上已录入期初的非末级科目（可修改/清零，避免脏数据无法修正）
    accounts = [a for a in db.query(Account).filter(Account.is_leaf == 1).order_by(Account.code).all()]
    for a in db.query(Account).filter(Account.is_leaf == 0).order_by(Account.code).all():
        if a.id in obs:
            accounts.append(a)
    for a in accounts:
        o = obs.get(a.id)
        d = L.r2(o.debit) if o else 0.0
        c = L.r2(o.credit) if o else 0.0
        td, tc = L.r2(td + d), L.r2(tc + c)
        rows.append({"account_id": a.id, "code": a.code, "name": a.name,
                     "direction": a.direction, "debit": d, "credit": c,
                     "is_leaf": bool(a.is_leaf),
                     "quantity": o.quantity if o else 0})
    return {"year": year, "rows": rows, "total_debit": td, "total_credit": tc,
            "balanced": abs(td - tc) < 0.005}


@router.put("/openings/save")
def save_openings(body: dict, db: Session = Depends(get_db)):
    """保存/修改期初余额。

    - 同一科目在提交中重复出现时报错，防止金额错位。
    - 逐行校验借贷互斥、非负、两位小数。
    - 保存后按“全年合并口径”校验试算平衡（而非仅本次提交行），
      防止分批修改后全年期初不平。
    """
    year = str(body.get("year") or "")[:4]
    if not year.isdigit():
        raise HTTPException(400, "年份无效")
    rows = body.get("rows") or []
    seen = set()
    for r in rows:
        aid = r.get("account_id")
        if aid in seen:
            raise HTTPException(400, f"提交的期初行中存在重复科目（account_id={aid}），请合并后再保存")
        seen.add(aid)
        acc = db.query(Account).get(aid)
        if not acc:
            continue
        existed = db.query(OpeningBalance).filter(
            OpeningBalance.account_id == aid, OpeningBalance.year == year).first()
        if not acc.is_leaf and not existed:
            raise HTTPException(400, f"科目 {acc.code} 不是末级科目，不能录入期初")
        d = L.r2(r.get("debit", 0) or 0)
        c = L.r2(r.get("credit", 0) or 0)
        if d < 0 or c < 0:
            raise HTTPException(400, f"科目 {acc.code} 期初金额不能为负")
        if d and c:
            raise HTTPException(400, f"科目 {acc.code} 期初借贷不能同时有值")
        if abs(float(r.get("debit", 0) or 0) - d) > 1e-9 or abs(float(r.get("credit", 0) or 0) - c) > 1e-9:
            raise HTTPException(400, f"科目 {acc.code} 期初金额最多两位小数")
        o = existed
        if not o:
            o = OpeningBalance(account_id=aid, year=year)
            db.add(o)
        o.debit, o.credit, o.quantity = d, c, r.get("quantity", 0) or 0
    db.flush()
    # 全年合并口径校验试算平衡
    total_d = total_c = 0.0
    for o in db.query(OpeningBalance).filter(OpeningBalance.year == year).all():
        total_d, total_c = L.r2(total_d + (o.debit or 0)), L.r2(total_c + (o.credit or 0))
    if abs(total_d - total_c) >= 0.005:
        db.rollback()
        raise HTTPException(
            400, f"期初试算不平衡：借方 {total_d:.2f} ≠ 贷方 {total_c:.2f}（含该年度已有期初），不能保存")
    db.commit()
    return {"ok": True, "total_debit": total_d, "total_credit": total_c}
