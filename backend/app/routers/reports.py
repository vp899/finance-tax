"""财务报表 + 报表导出"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..services import ledger as L
from ..services import excel_io as X
from ..services import report_excel as RX

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/balance-sheet")
def balance_sheet(period: str, db: Session = Depends(get_db)):
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return L.balance_sheet(db, period)


@router.get("/income")
def income(period: str, mode: str = "month", db: Session = Depends(get_db)):
    """mode=month 利润表；mode=quarter 利润表季报"""
    if not L.valid_period(period):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return L.income_statement(db, period, mode)


@router.get("/cashflow")
def cashflow(from_period: str, to_period: str, db: Session = Depends(get_db)):
    if not (L.valid_period(from_period) and L.valid_period(to_period)):
        raise HTTPException(400, "期间格式应为 YYYY-MM")
    return L.cashflow_statement(db, from_period, to_period)


def _stream(buf, filename):
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/{kind}")
def export_report(kind: str, period: str = None, from_period: str = None,
                  to_period: str = None, mode: str = "month",
                  db: Session = Depends(get_db)):
    period = period or to_period
    if kind == "balance-sheet":
        if not L.valid_period(period):
            raise HTTPException(400, "期间格式应为 YYYY-MM")
        return _stream(RX.export_balance_sheet_twocol(db, period),
                       f"balance_sheet_{period}.xlsx")
    if kind == "income":
        if not L.valid_period(period):
            raise HTTPException(400, "期间格式应为 YYYY-MM")
        # 标准表样：本年累计 + 四个季度列（月报/季报导出同一表样）
        return _stream(RX.export_income_standard(db, period[:4]),
                       f"income_{period[:4]}.xlsx")
    if kind == "cashflow":
        if not L.valid_period(period):
            raise HTTPException(400, "期间格式应为 YYYY-MM")
        return _stream(RX.export_cashflow_standard(db, period),
                       f"cashflow_{period}.xlsx")
    if kind == "voucher-summary":
        fp = from_period or f"{period[:4]}-01"
        tp = to_period or period
        data = L.voucher_summary(db, fp, tp)
        headers = ["凭证类型", "凭证张数", "借方合计", "贷方合计"]
        rows = [[r["vtype"], r["count"], r["debit"], r["credit"]] for r in data["rows"]]
        rows.append(["合计", data["count"], data["total_debit"], data["total_credit"]])
        return _stream(X.export_table("凭证汇总表", headers, rows, [2, 3]),
                       f"voucher_summary_{fp}_{tp}.xlsx")
    raise HTTPException(404, f"未知报表类型：{kind}")
