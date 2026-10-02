"""结转、结账、固定资产/无形资产管理"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import FixedAsset, IntangibleAsset, Period
from ..services import ledger as L
from ..services import carryover as C

router = APIRouter(prefix="/api/carryover", tags=["carryover"])


@router.get("/kinds")
def kinds(db: Session = Depends(get_db)):
    """全部结转步骤定义（名称/顺序/分录说明/金额来源）"""
    return [{**C.STEP_META[k], "order": v["order"], "enabled": v["enabled"],
             "amount_mode": v["amount_mode"], "default_amount": v["default_amount"],
             "accounts": v["accounts"]}
            for k, v in sorted(C.get_config(db)["steps"].items(),
                               key=lambda kv: (kv[1]["order"], kv[0]))]


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    return C.get_config(db)


@router.put("/config")
def put_config(body: dict, db: Session = Depends(get_db)):
    try:
        cfg = C.save_config(db, body)
        db.commit()
        return cfg
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.get("/preview/{kind}")
def preview(kind: str, period: str, withheld: float = None, vat_base: float = None,
            db: Session = Depends(get_db)):
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    kind = kind.replace("-", "_")
    if kind not in C.PLANNERS:
        raise HTTPException(404, f"未知结转类型：{kind}")
    extra = {}
    if withheld is not None:
        extra["withheld"] = withheld
    if vat_base is not None:
        extra["vat_base"] = vat_base
    return C.preview(kind, db, period, extra=extra)


@router.get("/records")
def records(period: str = None, year: str = None, from_period: str = None,
            to_period: str = None, db: Session = Depends(get_db)):
    return C.list_records(db, period=period, year=year,
                          from_period=from_period, to_period=to_period)


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

@router.post("/run-all")
def run_all(body: dict, db: Session = Depends(get_db)):
    """一键结转：按配置顺序执行结转步骤，返回每步结果"""
    period = str(body.get("period") or "")
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    try:
        res = C.run_all(db, period, kinds=body.get("kinds"),
                        amounts=body.get("amounts") or {},
                        stop_on_error=bool(body.get("stop_on_error")))
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.post("/{kind}")
def execute(kind: str, body: dict, db: Session = Depends(get_db)):
    period = str(body.get("period") or "")
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    kind = kind.replace("-", "_")
    if kind not in C.PLANNERS:
        raise HTTPException(404, f"未知结转类型：{kind}")
    try:
        amount = body.get("amount")
        extra = {}
        if body.get("withheld") is not None:
            extra["withheld"] = body.get("withheld")
        if body.get("vat_base") is not None:
            extra["vat_base"] = body.get("vat_base")
        res = C.execute(kind, db, period,
                        amount=float(amount) if amount not in (None, "") else None,
                        extra=extra, summary=body.get("summary") or None)
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
