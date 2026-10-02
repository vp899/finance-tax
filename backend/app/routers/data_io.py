"""数据导入导出 + 数据库备份/恢复"""
import os
import shutil
import tempfile
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db, DB_PATH, engine, Base
from ..models import Account
from ..services import ledger as L
from ..services import excel_io as X

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
        data.append(["", "合计", "", "", "", "", tb["total_debit"], tb["total_credit"]])
        return _stream(X.export_table("试算平衡表",
                                      ["科目编码", "科目名称", "期初借方", "期初贷方",
                                       "本期借方", "本期贷方", "期末借方", "期末贷方"],
                                      data, [2, 3, 4, 5, 6, 7]),
                       f"trial_balance_{fp}_{tp}.xlsx")
    raise HTTPException(404, f"未知账簿类型：{kind}")


@router.get("/template/vouchers")
def template():
    return _stream(X.voucher_template(), "voucher_import_template.xlsx")


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
def backup_info():
    return {
        "db_path": DB_PATH,
        "size_bytes": os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
        "created_at": datetime.fromtimestamp(os.path.getmtime(DB_PATH)).isoformat()
        if os.path.exists(DB_PATH) else None,
    }


@router.get("/backup/download")
def backup_download():
    """备份数据库为单个 SQLite 文件"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = os.path.join(tempfile.gettempdir(), f"finance_backup_{ts}.db")
    src = engine.raw_connection()
    try:
        dst = __import__("sqlite3").connect(tmp)
        src.backup(dst)
        dst.close()
    finally:
        src.close()
    fname = f"finance_backup_{ts}.db"

    def iterfile():
        with open(tmp, "rb") as f:
            yield from f
        os.remove(tmp)

    return StreamingResponse(iterfile(), media_type="application/octet-stream",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.post("/backup/restore")
async def backup_restore(file: UploadFile = File(...)):
    """从 SQLite 备份文件恢复（覆盖当前数据库）"""
    data = await file.read()
    if len(data) < 100 or not data.startswith(b"SQLite format 3"):
        raise HTTPException(400, "不是有效的 SQLite 备份文件")
    tmp = DB_PATH + ".restore"
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
    engine.dispose()
    shutil.move(tmp, DB_PATH)
    for suffix in ("-wal", "-shm"):
        p = DB_PATH + suffix
        if os.path.exists(p):
            os.remove(p)
    Base.metadata.create_all(bind=engine)
    return {"ok": True, "restored_bytes": len(data)}
