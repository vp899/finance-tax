"""结转、结账、固定资产/无形资产管理"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import FixedAsset, IntangibleAsset, Period
from ..services import ledger as L
from ..services import carryover as C

router = APIRouter(prefix="/api/carryover", tags=["carryover"])


@router.get("/preview/{kind}")
def preview(kind: str, period: str, db: Session = Depends(get_db)):
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    kind = kind.replace("-", "_")
    fn = {
        "sales_cost": C.preview_sales_cost, "salary": C.preview_salary,
        "depreciation": C.preview_depreciation, "amortization": C.preview_amortization,
        "profit": C.preview_profit, "tax": C.preview_tax,
        "income_tax": C.preview_income_tax, "vat_free": C.preview_vat_free,
    }.get(kind)
    if not fn:
        raise HTTPException(404, f"未知结转类型：{kind}")
    return fn(db, period)

@router.get("/records")
def records(period: str = None, db: Session = Depends(get_db)):
    return C.list_records(db, period)


@router.post("/reverse/{record_id}")
def reverse(record_id: int, db: Session = Depends(get_db)):
    try:
        res = C.reverse(db, record_id)
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.get("/periods")
def periods(db: Session = Depends(get_db)):
    rows = [{"period": p.period, "status": p.status, "closed_at": p.closed_at}
            for p in db.query(Period).order_by(Period.period.desc()).all()]
    return rows


@router.post("/close")
def close(body: dict, db: Session = Depends(get_db)):
    period = str(body.get("period") or "")
    try:
        res = C.close_period(db, period, force=bool(body.get("force")))
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.post("/open")
def open_(body: dict, db: Session = Depends(get_db)):
    try:
        res = C.open_period(db, str(body.get("period") or ""))
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


# ---------- 固定资产 / 无形资产 ----------

@router.get("/assets/fixed")
def list_fixed(db: Session = Depends(get_db)):
    return [{"id": f.id, "name": f.name, "original_value": f.original_value,
             "residual_rate": f.residual_rate, "life_months": f.life_months,
             "expense_account_code": f.expense_account_code, "dept": f.dept,
             "in_use": bool(f.in_use),
             "monthly_depreciation": L.r2(f.original_value * (1 - (f.residual_rate or 0)) / (f.life_months or 1))}
            for f in db.query(FixedAsset).order_by(FixedAsset.id).all()]


@router.post("/assets/fixed")
def create_fixed(body: dict, db: Session = Depends(get_db)):
    f = FixedAsset(
        name=body.get("name") or "固定资产",
        original_value=float(body.get("original_value") or 0),
        residual_rate=float(body.get("residual_rate") if body.get("residual_rate") is not None else 0.05),
        life_months=int(body.get("life_months") or 120),
        expense_account_code=body.get("expense_account_code") or "560202",
        dept=body.get("dept") or "",
    )
    db.add(f)
    db.commit()
    return {"id": f.id}


@router.put("/assets/fixed/{asset_id}")
def update_fixed(asset_id: int, body: dict, db: Session = Depends(get_db)):
    f = db.query(FixedAsset).get(asset_id)
    if not f:
        raise HTTPException(404, "固定资产不存在")
    for k in ("name", "expense_account_code", "dept"):
        if k in body:
            setattr(f, k, body[k])
    for k in ("original_value", "residual_rate"):
        if k in body:
            setattr(f, k, float(body[k]))
    if "life_months" in body:
        f.life_months = int(body["life_months"])
    if "in_use" in body:
        f.in_use = 1 if body["in_use"] else 0
    db.commit()
    return {"ok": True}


@router.delete("/assets/fixed/{asset_id}")
def delete_fixed(asset_id: int, db: Session = Depends(get_db)):
    db.query(FixedAsset).filter(FixedAsset.id == asset_id).delete()
    db.commit()
    return {"ok": True}


@router.get("/assets/intangible")
def list_intangible(db: Session = Depends(get_db)):
    return [{"id": f.id, "name": f.name, "original_value": f.original_value,
             "amort_months": f.amort_months,
             "expense_account_code": f.expense_account_code,
             "in_use": bool(f.in_use),
             "monthly_amortization": L.r2(f.original_value / (f.amort_months or 1))}
            for f in db.query(IntangibleAsset).order_by(IntangibleAsset.id).all()]


@router.post("/assets/intangible")
def create_intangible(body: dict, db: Session = Depends(get_db)):
    f = IntangibleAsset(
        name=body.get("name") or "无形资产",
        original_value=float(body.get("original_value") or 0),
        amort_months=int(body.get("amort_months") or 120),
        expense_account_code=body.get("expense_account_code") or "560203",
    )
    db.add(f)
    db.commit()
    return {"id": f.id}


@router.put("/assets/intangible/{asset_id}")
def update_intangible(asset_id: int, body: dict, db: Session = Depends(get_db)):
    f = db.query(IntangibleAsset).get(asset_id)
    if not f:
        raise HTTPException(404, "无形资产不存在")
    for k in ("name", "expense_account_code"):
        if k in body:
            setattr(f, k, body[k])
    if "original_value" in body:
        f.original_value = float(body["original_value"])
    if "amort_months" in body:
        f.amort_months = int(body["amort_months"])
    if "in_use" in body:
        f.in_use = 1 if body["in_use"] else 0
    db.commit()
    return {"ok": True}


@router.delete("/assets/intangible/{asset_id}")
def delete_intangible(asset_id: int, db: Session = Depends(get_db)):
    db.query(IntangibleAsset).filter(IntangibleAsset.id == asset_id).delete()
    db.commit()
    return {"ok": True}


# ---------- 结转执行（通配路由，必须定义在 /close、/open 等具体路由之后） ----------

@router.post("/{kind}")
def execute(kind: str, body: dict, db: Session = Depends(get_db)):
    period = str(body.get("period") or "")
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    kind = kind.replace("-", "_")
    try:
        if kind == "sales_cost":
            res = C.do_sales_cost(db, period, float(body.get("amount") or 0),
                                  body.get("summary") or "结转本月销售成本")
        elif kind == "salary":
            res = C.do_salary(db, period, float(body.get("amount") or 0),
                              body.get("expense_code"), body.get("summary") or "计提本月职工工资")
        elif kind == "depreciation":
            res = C.do_depreciation(db, period)
        elif kind == "amortization":
            res = C.do_amortization(db, period)
        elif kind == "profit":
            res = C.do_profit(db, period)
        elif kind == "tax":
            base = body.get("vat_base")
            res = C.do_tax(db, period, float(base) if base is not None else None)
        elif kind == "income_tax":
            amt = body.get("amount")
            res = C.do_income_tax(db, period, float(amt) if amt is not None else None)
        elif kind == "vat_free":
            amt = body.get("amount")
            res = C.do_vat_free(db, period, float(amt) if amt is not None else None)
        else:
            raise HTTPException(404, f"未知结转类型：{kind}")
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
