"""财税设置：基本设置、凭证类型、计量单位、币种、现金流量项目、科目现金流量对照表"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    Setting, VoucherType, Unit, Currency, CashflowItem, AccountCashflowMap, Account,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.query(Setting).all()}


@router.put("")
def put_settings(body: dict, db: Session = Depends(get_db)):
    for k, v in body.items():
        s = db.query(Setting).filter(Setting.key == k).first()
        if not s:
            s = Setting(key=k)
            db.add(s)
        s.value = str(v)
    db.commit()
    return {"ok": True}


# 凭证类型
@router.get("/voucher-types")
def list_vtypes(db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "prefix": t.prefix, "is_default": bool(t.is_default)}
            for t in db.query(VoucherType).order_by(VoucherType.id).all()]


@router.post("/voucher-types")
def create_vtype(body: dict, db: Session = Depends(get_db)):
    name = (body.get("name") or "").strip()
    prefix = (body.get("prefix") or "").strip()
    if not name or not prefix:
        raise HTTPException(400, "名称与前缀必填")
    if db.query(VoucherType).filter(VoucherType.prefix == prefix).first():
        raise HTTPException(400, f"前缀已存在：{prefix}")
    t = VoucherType(name=name, prefix=prefix, is_default=1 if body.get("is_default") else 0)
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.delete("/voucher-types/{item_id}")
def delete_vtype(item_id: int, db: Session = Depends(get_db)):
    db.query(VoucherType).filter(VoucherType.id == item_id).delete()
    db.commit()
    return {"ok": True}


# 计量单位
@router.get("/units")
def list_units(db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.name, "symbol": u.symbol}
            for u in db.query(Unit).order_by(Unit.id).all()]


@router.post("/units")
def create_unit(body: dict, db: Session = Depends(get_db)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "单位名称必填")
    if db.query(Unit).filter(Unit.name == name).first():
        raise HTTPException(400, f"单位已存在：{name}")
    u = Unit(name=name, symbol=body.get("symbol") or "")
    db.add(u)
    db.commit()
    return {"id": u.id}


@router.delete("/units/{item_id}")
def delete_unit(item_id: int, db: Session = Depends(get_db)):
    db.query(Unit).filter(Unit.id == item_id).delete()
    db.commit()
    return {"ok": True}


# 币种
@router.get("/currencies")
def list_currencies(db: Session = Depends(get_db)):
    return [{"id": c.id, "code": c.code, "name": c.name, "rate": c.rate,
             "is_default": bool(c.is_default)}
            for c in db.query(Currency).order_by(Currency.code).all()]


@router.post("/currencies")
def create_currency(body: dict, db: Session = Depends(get_db)):
    code = (body.get("code") or "").strip().upper()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "币种代码与名称必填")
    if db.query(Currency).filter(Currency.code == code).first():
        raise HTTPException(400, f"币种已存在：{code}")
    c = Currency(code=code, name=name, rate=float(body.get("rate") or 1),
                 is_default=1 if body.get("is_default") else 0)
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.put("/currencies/{item_id}")
def update_currency(item_id: int, body: dict, db: Session = Depends(get_db)):
    c = db.query(Currency).get(item_id)
    if not c:
        raise HTTPException(404, "币种不存在")
    if "rate" in body:
        c.rate = float(body["rate"])
    if "name" in body:
        c.name = body["name"]
    db.commit()
    return {"ok": True}


@router.delete("/currencies/{item_id}")
def delete_currency(item_id: int, db: Session = Depends(get_db)):
    db.query(Currency).filter(Currency.id == item_id).delete()
    db.commit()
    return {"ok": True}


# 现金流量项目
@router.get("/cashflow-items")
def list_cashflow_items(db: Session = Depends(get_db)):
    return [{"code": c.code, "name": c.name, "category": c.category,
             "direction": c.direction}
            for c in db.query(CashflowItem).order_by(CashflowItem.code).all()]


@router.post("/cashflow-items")
def create_cashflow_item(body: dict, db: Session = Depends(get_db)):
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "项目编码与名称必填")
    if db.query(CashflowItem).filter(CashflowItem.code == code).first():
        raise HTTPException(400, f"项目编码已存在：{code}")
    db.add(CashflowItem(code=code, name=name,
                        category=body.get("category") or "operating",
                        direction=body.get("direction") or "D"))
    db.commit()
    return {"ok": True}


@router.delete("/cashflow-items/{code}")
def delete_cashflow_item(code: str, db: Session = Depends(get_db)):
    db.query(AccountCashflowMap).filter(AccountCashflowMap.cashflow_code == code).delete()
    db.query(CashflowItem).filter(CashflowItem.code == code).delete()
    db.commit()
    return {"ok": True}


# 科目现金流量对照表
@router.get("/cashflow-map")
def list_cashflow_map(db: Session = Depends(get_db)):
    rows = []
    for m in db.query(AccountCashflowMap).all():
        acc = db.query(Account).get(m.account_id)
        rows.append({"id": m.id, "account_id": m.account_id,
                     "account_code": acc.code if acc else "",
                     "account_name": acc.name if acc else "",
                     "cashflow_code": m.cashflow_code})
    rows.sort(key=lambda r: r["account_code"])
    return rows


@router.post("/cashflow-map")
def upsert_cashflow_map(body: dict, db: Session = Depends(get_db)):
    acc = db.query(Account).get(body.get("account_id"))
    if not acc:
        raise HTTPException(400, "科目不存在")
    code = (body.get("cashflow_code") or "").strip()
    if not db.query(CashflowItem).filter(CashflowItem.code == code).first():
        raise HTTPException(400, f"现金流量项目不存在：{code}")
    m = db.query(AccountCashflowMap).filter(AccountCashflowMap.account_id == acc.id).first()
    if not m:
        m = AccountCashflowMap(account_id=acc.id, cashflow_code=code)
        db.add(m)
    else:
        m.cashflow_code = code
    acc.cashflow_code = code
    db.commit()
    return {"ok": True}


@router.delete("/cashflow-map/{item_id}")
def delete_cashflow_map(item_id: int, db: Session = Depends(get_db)):
    db.query(AccountCashflowMap).filter(AccountCashflowMap.id == item_id).delete()
    db.commit()
    return {"ok": True}
