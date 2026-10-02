"""账簿查询"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..services import ledger as L

router = APIRouter(prefix="/api/books", tags=["books"])


def _range_params(period: str = None, year: str = None,
                  from_period: str = None, to_period: str = None):
    """统一解析查询口径：单期间 / 年度 / 起止区间"""
    if period:
        if not L.valid_period(period):
            raise HTTPException(400, "期间格式应为 YYYY-MM")
        return period, period
    if year:
        if not (year.isdigit() and len(year) == 4):
            raise HTTPException(400, "年份格式应为 YYYY")
        return f"{year}-01", f"{year}-12"
    if from_period and to_period:
        if not (L.valid_period(from_period) and L.valid_period(to_period)):
            raise HTTPException(400, "期间格式应为 YYYY-MM")
        if from_period > to_period:
            raise HTTPException(400, "起始期间不能晚于截止期间")
        return from_period, to_period
    raise HTTPException(400, "请指定期间 period、年度 year 或起止区间 from_period/to_period")


@router.get("/general-ledger")
def general_ledger(period: str = None, year: str = None, from_period: str = None,
                   to_period: str = None, db: Session = Depends(get_db)):
    fp, tp = _range_params(period, year, from_period, to_period)
    rows = L.general_ledger(db, period=fp if fp == tp else None,
                            from_period=fp, to_period=tp)
    return {"period": tp, "from_period": fp, "to_period": tp, "rows": rows}


@router.get("/balance-table")
def balance_table(period: str = None, year: str = None, from_period: str = None,
                  to_period: str = None, db: Session = Depends(get_db)):
    """余额表"""
    fp, tp = _range_params(period, year, from_period, to_period)
    rows = L.balance_table(db, period=fp if fp == tp else None,
                           from_period=fp, to_period=tp)
    return {"period": tp, "from_period": fp, "to_period": tp, "rows": rows}


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
def trial_balance(period: str = None, year: str = None, from_period: str = None,
                  to_period: str = None, db: Session = Depends(get_db)):
    """试算平衡表（支持单期间 / 年度 / 起止区间）"""
    fp, tp = _range_params(period, year, from_period, to_period)
    try:
        return L.trial_balance(db, from_period=fp, to_period=tp)
    except ValueError as e:
        raise HTTPException(400, str(e))
