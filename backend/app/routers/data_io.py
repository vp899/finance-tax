"""数据导入导出 + 数据库备份/恢复"""
import os
import shutil
import tempfile
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import (
    get_db, get_book_id, book_db_path, book_engine, DB_PATH, engine, Base,
)
from ..models import Account
from ..services import ledger as L
from ..services import excel_io as X
from ..services import detail_io as D

router = APIRouter(prefix="/api/data", tags=["data"])


def _stream(buf, filename):
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/vouchers")
def export_vouchers(from_period: str, to_period: str, db: Session = Depends(get_db)):
    return _stream(X.export_vouchers(db, from_period, to_period),
                   f"vouchers_{from_period}_{to_period}.xlsx")


@router.get("/export/book/{kind}")
def export_book(kind: str, period: str = None, from_period: str = None,
                to_period: str = None, account_code: str = None,
                db: Session = Depends(get_db)):
    fp = from_period or f"{period[:4]}-01"
    tp = to_period or period
    if kind == "general-ledger":
        rows = L.general_ledger(db, period=None, from_period=fp, to_period=tp)
        data = [[r["code"], r["name"], r["opening_debit"], r["opening_credit"],
                 r["period_debit"], r["period_credit"],
                 r["closing_debit"], r["closing_credit"]] for r in rows]
        return _stream(X.export_table("总账", ["科目编码", "科目名称", "期初借方", "期初贷方",
                                              "本期借方", "本期贷方", "期末借方", "期末贷方"],
                                      data, [2, 3, 4, 5, 6, 7]),
                       f"general_ledger_{fp}_{tp}.xlsx")
    if kind == "balance-table":
        rows = L.balance_table(db, period=None, from_period=fp, to_period=tp)
        data = [[r["code"], r["name"], r["opening_debit"], r["opening_credit"],
                 r["period_debit"], r["period_credit"],
                 r["closing_debit"], r["closing_credit"]] for r in rows]
        return _stream(X.export_table("余额表", ["科目编码", "科目名称", "期初借方", "期初贷方",
                                                "本期借方", "本期贷方", "期末借方", "期末贷方"],
                                      data, [2, 3, 4, 5, 6, 7]),
                       f"balance_table_{fp}_{tp}.xlsx")
    if kind == "detail":
        if not account_code:
            raise HTTPException(400, "缺少 account_code")
        d = L.detail_ledger(db, account_code, fp, tp)
        data = [[r["date"], r["voucher_no"], r["summary"], r["account_code"],
                 r["account_name"], r["debit"], r["credit"],
                 r["balance_debit"], r["balance_credit"]] for r in d["rows"]]
        return _stream(X.export_table("明细账", ["日期", "凭证号", "摘要", "科目编码", "科目名称",
                                                "借方", "贷方", "余额借方", "余额贷方"],
                                      data, [5, 6, 7, 8]),
                       f"detail_{account_code}_{fp}_{tp}.xlsx")
    if kind == "journal":
        rows = L.journal(db, fp, tp)
        data = [[r["date"], r["voucher_no"], r["vtype"], r["summary"], r["account_code"],
                 r["account_name"], r["debit"], r["credit"], r["quantity"], r["unit"]]
                for r in rows]
        return _stream(X.export_table("序时账", ["日期", "凭证号", "类型", "摘要", "科目编码",
                                                "科目名称", "借方", "贷方", "数量", "单位"],
                                      data, [6, 7]),
                       f"journal_{fp}_{tp}.xlsx")
    if kind == "multi-column":
        if not account_code:
            raise HTTPException(400, "缺少 account_code")
        d = L.multi_column_ledger(db, account_code, fp, tp)
        headers = ["日期", "凭证号", "摘要", "科目"] + [c["name"] for c in d["columns"]]
        data = []
        for r in d["rows"]:
            data.append([r["date"], r["voucher_no"], r["summary"], r["account_name"]] +
                        [r["columns"][c["code"]] for c in d["columns"]])
        return _stream(X.export_table("多栏账", headers, data, list(range(4, len(headers)))),
                       f"multicolumn_{account_code}_{fp}_{tp}.xlsx")
    if kind == "trial-balance":
        tb = L.trial_balance(db, from_period=fp, to_period=tp)
        data = [[r["code"], r["name"], r["opening_debit"], r["opening_credit"],
                 r["period_debit"], r["period_credit"], r["debit"], r["credit"]]
                for r in tb["rows"]]
        data.append(["", "合计",
                     tb.get("total_opening_debit", 0), tb.get("total_opening_credit", 0),
                     tb.get("total_period_debit", 0), tb.get("total_period_credit", 0),
                     tb["total_debit"], tb["total_credit"]])
        return _stream(X.export_table("试算平衡表",
                                      ["科目编码", "科目名称", "期初借方", "期初贷方",
                                       "本期借方", "本期贷方", "期末借方", "期末贷方"],
                                      data, [2, 3, 4, 5, 6, 7]),
                       f"trial_balance_{fp}_{tp}.xlsx")
    raise HTTPException(404, f"未知账簿类型：{kind}")


@router.get("/template/vouchers")
def template():
    return _stream(X.voucher_template(), "voucher_import_template.xlsx")


@router.get("/export/detail-ledger")
def export_detail_ledger(from_period: str = None, to_period: str = None,
                         period: str = None, account_code: str = None,
                         db: Session = Depends(get_db)):
    """导出明细账（序号 科目编码 科目 日期 凭证号 摘要 借方 贷方 方向 余额）"""
    fp = from_period or (f"{period[:4]}-01" if period else None)
    tp = to_period or period
    if not fp or not tp:
        raise HTTPException(400, "请指定期间 period 或起止区间 from_period/to_period")
    if not (L.valid_period(fp) and L.valid_period(tp)) or fp > tp:
        raise HTTPException(400, "期间格式应为 YYYY-MM，且起始期间不能晚于截止期间")
    return _stream(D.export_detail_ledger(db, account_code=account_code,
                                         from_period=fp, to_period=tp),
                   f"detail_ledger_{fp}_{tp}.xlsx")


@router.get("/template/detail-ledger")
def detail_ledger_template():
    return _stream(D.detail_ledger_template(), "detail_ledger_import_template.xlsx")


@router.post("/import/detail-ledger")
async def import_detail_ledger(file: UploadFile = File(...), opening_year: str = None,
                               db: Session = Depends(get_db)):
    """导入明细账：期初行→科目期初，记账行→凭证（同日期+凭证号合并）"""
    data = await file.read()
    try:
        res = D.import_detail_ledger(db, data, opening_year=opening_year)
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.post("/import/vouchers")
async def import_vouchers(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        res = X.import_vouchers(db, data)
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


# ---------------- 备份 / 恢复 ----------------

@router.get("/backup/info")
def backup_info(request: Request):
    bid = get_book_id(request)
    path = book_db_path(bid)
    return {
        "book_id": bid,
        "db_path": path,
        "size_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "created_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
        if os.path.exists(path) else None,
    }


@router.get("/backup/download")
def backup_download(request: Request):
    """备份当前账套数据库为单个 SQLite 文件"""
    bid = get_book_id(request)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = os.path.join(tempfile.gettempdir(), f"finance_backup_{bid}_{ts}.db")
    src = book_engine(bid).raw_connection()
    try:
        dst = __import__("sqlite3").connect(tmp)
        src.backup(dst)
        dst.close()
    finally:
        src.close()
    fname = f"finance_backup_{bid}_{ts}.db"

    def iterfile():
        with open(tmp, "rb") as f:
            yield from f
        os.remove(tmp)

    return StreamingResponse(iterfile(), media_type="application/octet-stream",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/backup/restore")
async def backup_restore(request: Request, file: UploadFile = File(...)):
    """从 SQLite 备份文件恢复（覆盖当前账套数据库）"""
    bid = get_book_id(request)
    db_path = book_db_path(bid)
    data = await file.read()
    if len(data) < 100 or not data.startswith(b"SQLite format 3"):
        raise HTTPException(400, "不是有效的 SQLite 备份文件")
    tmp = db_path + ".restore"
    with open(tmp, "wb") as f:
        f.write(data)
    # 校验可打开
    import sqlite3
    try:
        conn = sqlite3.connect(tmp)
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
    except Exception:
        os.remove(tmp)
        raise HTTPException(400, "备份文件损坏，无法恢复")
    book_engine(bid).dispose()
    shutil.move(tmp, db_path)
    for suffix in ("-wal", "-shm"):
        p = db_path + suffix
        if os.path.exists(p):
            os.remove(p)
    Base.metadata.create_all(bind=book_engine(bid))
    return {"ok": True, "restored_bytes": len(data), "book_id": bid}
