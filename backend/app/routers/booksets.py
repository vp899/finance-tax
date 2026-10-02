"""账套管理（多套账）：列表 / 新建 / 复制 / 重命名 / 设默认 / 删除"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import sessionmaker

from .. import database as D
from ..models import Account, OpeningBalance, Setting, Voucher
from ..services import ledger as L

router = APIRouter(prefix="/api/booksets", tags=["booksets"])


def _session_for(book_id: str):
    if book_id == D.DEFAULT_BOOK_ID:
        return D.SessionLocal()
    return sessionmaker(autocommit=False, autoflush=False,
                        bind=D.book_engine(book_id))()


@router.get("")
def list_booksets():
    """账套列表（含各账套概要）"""
    out = []
    for b in D.list_books():
        db = _session_for(b["id"])
        try:
            out.append({
                "id": b["id"], "name": b["name"], "remark": b.get("remark", ""),
                "created_at": b.get("created_at", ""),
                "is_default": bool(b.get("is_default")),
                "account_count": db.query(Account).count(),
                "voucher_count": db.query(Voucher).count(),
                "opening_year": L.get_setting(db, "opening_year", ""),
            })
        finally:
            db.close()
    return out


@router.post("")
def create_bookset(body: dict):
    """新建账套：copy_from 指定来源账套时整账套复制（含数据），否则初始化为空账套"""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "账套名称必填")
    opening_year = str(body.get("opening_year") or "").strip()
    if opening_year and not (opening_year.isdigit() and len(opening_year) == 4):
        raise HTTPException(400, "期初年份格式应为 YYYY")
    try:
        b = D.create_book(
            name=name,
            remark=body.get("remark") or "",
            copy_from=(body.get("copy_from") or "").strip() or None,
            book_id=(body.get("id") or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if opening_year:
        db = _session_for(b["id"])
        try:
            s = db.query(Setting).filter(Setting.key == "opening_year").first()
            if not s:
                s = Setting(key="opening_year")
                db.add(s)
            s.value = opening_year
            db.commit()
        finally:
            db.close()
    return {"id": b["id"], "name": b["name"]}


@router.put("/{book_id}")
def update_bookset(book_id: str, body: dict):
    try:
        if "name" in body or "remark" in body:
            D.update_book(book_id, **{k: body[k] for k in ("name", "remark") if k in body})
        if body.get("is_default"):
            D.set_default_book(book_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.delete("/{book_id}")
def delete_bookset(book_id: str):
    try:
        D.delete_book(book_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.get("/{book_id}/openings")
def bookset_openings(book_id: str, year: str = None):
    """查看指定账套的科目期初概况（用于账套切换前后核对）"""
    if not D.valid_book_id(book_id) or not D.get_book(book_id):
        raise HTTPException(404, f"账套不存在：{book_id}")
    db = _session_for(book_id)
    try:
        y = year or L.get_setting(db, "opening_year", "") or ""
        q = db.query(OpeningBalance)
        if y:
            q = q.filter(OpeningBalance.year == y)
        rows = q.all()
        return {
            "book_id": book_id, "year": y,
            "opening_year": L.get_setting(db, "opening_year", ""),
            "count": len(rows),
            "total_debit": L.r2(sum(o.debit or 0 for o in rows)),
            "total_credit": L.r2(sum(o.credit or 0 for o in rows)),
        }
    finally:
        db.close()
