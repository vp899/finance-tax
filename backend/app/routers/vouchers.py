"""凭证管理"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Account, Voucher, VoucherEntry
from ..services import ledger as L
from ..services import vouchers as V

router = APIRouter(prefix="/api/vouchers", tags=["vouchers"])


def _v2d(v: Voucher, with_entries=True):
    d = {
        "id": v.id, "voucher_no": v.voucher_no, "vtype": v.vtype, "date": v.date,
        "period": v.period, "status": v.status, "attachment_count": v.attachment_count,
        "source": v.source, "carryover_kind": v.carryover_kind,
        "remark": v.remark, "created_at": v.created_at,
    }
    if with_entries:
        total_d = total_c = 0.0
        entries = []
        for e in v.entries:
            a = e.account
            total_d, total_c = L.r2(total_d + e.debit), L.r2(total_c + e.credit)
            entries.append({
                "id": e.id, "line_no": e.line_no, "account_id": e.account_id,
                "account_code": a.code if a else "", "account_name": a.name if a else "",
                "summary": e.summary, "debit": e.debit, "credit": e.credit,
                "currency": e.currency, "quantity": e.quantity, "unit": e.unit,
                "cashflow_code": e.cashflow_code,
            })
        d["entries"] = entries
        d["total_debit"] = total_d
        d["total_credit"] = total_c
    return d


@router.get("")
def list_vouchers(period: str = None, year: str = None, from_period: str = None,
                  to_period: str = None, status: str = None, q: str = "",
                  page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    query = db.query(Voucher)
    if period:
        query = query.filter(Voucher.period == period)
    else:
        if year:
            query = query.filter(Voucher.period >= f"{year}-01", Voucher.period <= f"{year}-12")
        else:
            if from_period:
                query = query.filter(Voucher.period >= from_period)
            if to_period:
                query = query.filter(Voucher.period <= to_period)
    if status:
        query = query.filter(Voucher.status == status)
    if q:
        sub = db.query(VoucherEntry.voucher_id).filter(VoucherEntry.summary.like(f"%{q}%"))
        query = query.filter((Voucher.voucher_no.like(f"%{q}%")) |
                             (Voucher.remark.like(f"%{q}%")) |
                             Voucher.id.in_(sub))
    total = query.count()
    rows = query.order_by(Voucher.date.desc(), Voucher.voucher_no.desc()) \
        .offset((page - 1) * size).limit(size).all()
    out = []
    for v in rows:
        d = _v2d(v, with_entries=False)
        d["entry_count"] = len(v.entries)
        d["total_debit"] = L.r2(sum(e.debit for e in v.entries))
        d["first_summary"] = v.entries[0].summary if v.entries else ""
        out.append(d)
    return {"total": total, "page": page, "size": size, "rows": out}


@router.get("/summary")
def summary(from_period: str, to_period: str, db: Session = Depends(get_db)):
    """凭证汇总表"""
    return L.voucher_summary(db, from_period, to_period)


@router.get("/suggest")
def suggest(q: str = "", db: Session = Depends(get_db)):
    """智能补全：科目 + 摘要"""
    q = (q or "").strip()
    ql = q.lower()
    query = db.query(Account).filter(Account.is_disabled == 0)
    if ql:
        query = query.filter((Account.code.like(f"{ql}%")) |
                             (Account.name.like(f"%{q}%")) |
                             (Account.pinyin.like(f"%{ql}%")))
    accs = query.order_by(Account.code).limit(15).all()
    accounts = []
    for a in accs:
        bal = L.all_time_balance(db, [a.id])
        accounts.append({
            "id": a.id, "code": a.code, "name": a.name,
            "is_leaf": bool(a.is_leaf), "direction": a.direction,
            "balance": bal, "text": f"{a.code} {a.name}",
        })
    squery = db.query(VoucherEntry.summary).filter(VoucherEntry.summary != "")
    if q:
        squery = squery.filter(VoucherEntry.summary.like(f"%{q}%"))
    summaries = [s for (s,) in squery.distinct().order_by(VoucherEntry.id.desc()).limit(10).all()]
    return {"accounts": accounts, "summaries": summaries}


@router.post("")
def create_voucher(body: dict, db: Session = Depends(get_db)):
    try:
        v = V.create_voucher(
            db,
            date=str(body.get("date") or ""),
            vtype=body.get("vtype") or "记",
            entries=body.get("entries") or [],
            status=body.get("status") or "posted",
            source="manual",
            remark=body.get("remark") or "",
            voucher_no=body.get("voucher_no") or None,
        )
        if body.get("attachment_count"):
            v.attachment_count = int(body["attachment_count"])
        db.commit()
        db.refresh(v)
        return _v2d(v)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.get("/{voucher_id}")
def get_voucher(voucher_id: int, db: Session = Depends(get_db)):
    v = db.query(Voucher).get(voucher_id)
    if not v:
        raise HTTPException(404, "凭证不存在")
    return _v2d(v)


@router.put("/{voucher_id}")
def update_voucher(voucher_id: int, body: dict, db: Session = Depends(get_db)):
    v = db.query(Voucher).get(voucher_id)
    if not v:
        raise HTTPException(404, "凭证不存在")
    if v.status == "voided":
        raise HTTPException(400, "已作废凭证不能修改")
    if V.is_period_closed(db, v.period):
        raise HTTPException(400, f"期间 {v.period} 已结账，不能修改凭证")
    try:
        date = str(body.get("date") or v.date)
        if date[:7] != v.period:
            if V.is_period_closed(db, date[:7]):
                raise ValueError(f"目标期间 {date[:7]} 已结账")
            v.period = date[:7]
        v.date = date
        v.vtype = body.get("vtype") or v.vtype
        v.remark = (body.get("remark") or "")[:200]
        v.attachment_count = int(body.get("attachment_count") or 0)
        entries = body.get("entries") or []
        amap, errors = V.validate_entries(db, entries)
        if errors:
            raise ValueError("；".join(errors))
        entries = V.auto_cashflow(db, entries, amap)
        V.build_entries(v, entries, amap,
                        qty_dp=int(L.get_setting(db, "decimal_qty", "2") or 2),
                        rate_dp=int(L.get_setting(db, "decimal_rate", "6") or 6))
        db.commit()
        db.refresh(v)
        return _v2d(v)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.post("/{voucher_id}/void")
def void_voucher(voucher_id: int, db: Session = Depends(get_db)):
    """作废/恢复凭证（保留凭证记录便于追溯）；同步结转记录状态"""
    from ..models import CarryoverRecord
    v = db.query(Voucher).get(voucher_id)
    if not v:
        raise HTTPException(404, "凭证不存在")
    if V.is_period_closed(db, v.period):
        raise HTTPException(400, f"期间 {v.period} 已结账，不能作废凭证")
    new_status = "voided" if v.status != "voided" else "posted"
    v.status = new_status
    for rec in db.query(CarryoverRecord).filter(CarryoverRecord.voucher_id == voucher_id).all():
        rec.status = "reversed" if new_status == "voided" else "active"
    db.commit()
    return {"id": v.id, "status": v.status}


@router.post("/{voucher_id}/copy")
def copy_voucher(voucher_id: int, db: Session = Depends(get_db)):
    v = db.query(Voucher).get(voucher_id)
    if not v:
        raise HTTPException(404, "凭证不存在")
    entries = [{
        "account_id": e.account_id, "summary": e.summary,
        "debit": e.debit, "credit": e.credit,
        "quantity": e.quantity, "unit": e.unit, "cashflow_code": e.cashflow_code,
    } for e in v.entries]
    try:
        nv = V.create_voucher(db, date=v.date, vtype=v.vtype, entries=entries,
                              source="manual", remark=f"复制自 {v.voucher_no}")
        db.commit()
        db.refresh(nv)
        return _v2d(nv)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.delete("/{voucher_id}")
def delete_voucher(voucher_id: int, db: Session = Depends(get_db)):
    """删除凭证（不可恢复）；结转生成的凭证同时删除其结转记录"""
    from ..models import CarryoverRecord
    v = db.query(Voucher).get(voucher_id)
    if not v:
        raise HTTPException(404, "凭证不存在")
    if V.is_period_closed(db, v.period):
        raise HTTPException(400, f"期间 {v.period} 已结账，不能删除凭证")
    no = v.voucher_no
    removed = db.query(CarryoverRecord).filter(
        CarryoverRecord.voucher_id == voucher_id).delete(synchronize_session=False)
    db.delete(v)
    db.commit()
    return {"ok": True, "voucher_no": no, "carryover_records_removed": removed}
