"""账簿查询"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..services import ledger as L

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("/general-ledger")
def general_ledger(period: str, db: Session = Depends(get_db)):
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return {"period": period, "rows": L.general_ledger(db, period)}


@router.get("/balance-table")
def balance_table(period: str, db: Session = Depends(get_db)):
    """余额表"""
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return {"period": period, "rows": L.balance_table(db, period)}


@router.get("/detail")
def detail_ledger(account_code: str, from_period: str, to_period: str,
                  rollup: bool = True, db: Session = Depends(get_db)):
    """明细账"""
    if not (L.valid_period(from_period) and L.valid_period(to_period)):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return L.detail_ledger(db, account_code, from_period, to_period, rollup)


@router.get("/journal")
def journal(from_period: str, to_period: str, db: Session = Depends(get_db)):
    """序时账"""
    if not (L.valid_period(from_period) and L.valid_period(to_period)):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    rows = L.journal(db, from_period, to_period)
    return {"rows": rows,
            "total_debit": L.r2(sum(r["debit"] for r in rows)),
            "total_credit": L.r2(sum(r["credit"] for r in rows))}


@router.get("/multi-column")
def multi_column(account_code: str, from_period: str, to_period: str,
                 db: Session = Depends(get_db)):
    """多栏账"""
    if not (L.valid_period(from_period) and L.valid_period(to_period)):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return L.multi_column_ledger(db, account_code, from_period, to_period)


@router.get("/trial-balance")
def trial_balance(period: str, db: Session = Depends(get_db)):
    """试算平衡表"""
    return L.trial_balance(db, period)
