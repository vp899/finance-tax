"""科目管理 + 科目期初 + 科目表/期初导入导出 + 数据清零"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    Account, OpeningBalance, OpeningBalanceItem, VoucherEntry, Voucher, CarryoverRecord,
    Period, Setting,
)
from ..services import ledger as L
from ..services import excel_io as X

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# 核算类型 ↔ 中文
CATEGORY_NAMES = {
    "asset": "资产", "liability": "负债", "equity": "权益",
    "cost": "成本", "income": "损益-收入", "expense": "损益-费用",
}
CATEGORY_VALUES = set(CATEGORY_NAMES)
AUX_FIELDS = ["aux_project", "aux_customer", "aux_supplier",
              "aux_dept", "aux_employee", "aux_inventory"]


def _acc2d(a: Account, opening: dict = None) -> dict:
    d = {
        "id": a.id, "code": a.code, "name": a.name, "parent_code": a.parent_code,
        "direction": a.direction, "category": a.category,
        "category_name": CATEGORY_NAMES.get(a.category, a.category),
        "pinyin": a.pinyin,
        "is_leaf": bool(a.is_leaf), "is_disabled": bool(a.is_disabled),
        "quantity_accounting": bool(a.quantity_accounting),
        "level": a.level, "currency": a.currency, "unit": a.unit,
        "cashflow_code": a.cashflow_code, "remark": a.remark,
    }
    for f in AUX_FIELDS:
        d[f] = bool(getattr(a, f))
    if opening is not None:
        d["opening"] = opening
    return d


def _opening_of(db: Session, account_id: int, as_of: str = None) -> dict:
    """科目自身（不含下级）的期初/年初余额；as_of=YYYY-MM 时为该期间期初"""
    o = db.query(OpeningBalance).filter(
        OpeningBalance.account_id == account_id,
        OpeningBalance.year == (as_of or "")[:4]).first() if as_of else None
    if as_of:
        od, oc = L.opening_sums(db, [account_id], as_of)
        return {"debit": od, "credit": oc,
                "year_debit": L.r2(o.debit) if o else 0.0,
                "year_credit": L.r2(o.credit) if o else 0.0,
                "quantity": (o.quantity if o else 0) or 0}
    return {"debit": 0.0, "credit": 0.0, "year_debit": 0.0, "year_credit": 0.0, "quantity": 0}


@router.get("")
def list_accounts(as_of: str = None, include_disabled: bool = True,
                  db: Session = Depends(get_db)):
    rows = []
    for a in db.query(Account).order_by(Account.code).all():
        if not include_disabled and a.is_disabled:
            continue
        rows.append(_acc2d(a, opening=_opening_of(db, a.id, as_of)))
    return rows


@router.get("/suggest")
def suggest(q: str = "", db: Session = Depends(get_db)):
    """智能补全：按编码/名称/拼音匹配科目，附带当前余额（停用科目不参与）"""
    q = (q or "").strip().lower()
    query = db.query(Account).filter(Account.is_disabled == 0)
    if q:
        query = query.filter(
            (Account.code.like(f"{q}%")) |
            (Account.name.like(f"%{q}%")) |
            (Account.pinyin.like(f"%{q}%"))
        )
    accs = query.order_by(Account.code).limit(30).all()
    out = []
    for a in accs:
        bal = L.all_time_balance(db, [a.id])
        out.append({
            "id": a.id, "code": a.code, "name": a.name,
            "is_leaf": bool(a.is_leaf), "direction": a.direction,
            "balance": bal, "text": f"{a.code} {a.name}",
        })
    return out


def _apply_fields(a: Account, body: dict, db: Session):
    for field in ("name", "pinyin", "direction", "currency", "unit", "remark"):
        if field in body and body[field] is not None:
            setattr(a, field, body[field])
    if "category" in body and body["category"]:
        if body["category"] not in CATEGORY_VALUES:
            raise HTTPException(400, f"核算类型无效：{body['category']}")
        a.category = body["category"]
    if "cashflow_code" in body:
        a.cashflow_code = body["cashflow_code"] or None
    for f in ("is_disabled", "quantity_accounting") + tuple(AUX_FIELDS):
        if f in body:
            setattr(a, f, 1 if body[f] else 0)


@router.post("")
def create_account(body: dict, db: Session = Depends(get_db)):
    code = (body.get("code") or "").strip()
    name = (body.get("name") or "").strip()
    if not code or not name:
        raise HTTPException(400, "科目编码和名称必填")
    if db.query(Account).filter(Account.code == code).first():
        raise HTTPException(400, f"科目编码已存在：{code}")
    parent_code = (body.get("parent_code") or "").strip() or None
    level = 1
    if parent_code:
        parent = L.account_by_code(db, parent_code)
        if not parent:
            raise HTTPException(400, f"上级科目不存在：{parent_code}")
        parent.is_leaf = 0
        level = parent.level + 1
    a = Account(
        code=code, name=name, parent_code=parent_code,
        direction=body.get("direction") or "D",
        category=body.get("category") or L.infer_category(code, body.get("direction") or "D"),
        pinyin=(body.get("pinyin") or "").strip(),
        is_leaf=1, level=level,
    )
    db.add(a)
    _apply_fields(a, body, db)
    db.commit()
    return {"id": a.id, "code": a.code, "name": a.name}


@router.put("/{account_id}")
def update_account(account_id: int, body: dict, db: Session = Depends(get_db)):
    a = db.query(Account).get(account_id)
    if not a:
        raise HTTPException(404, "科目不存在")
    if "parent_code" in body:
        new_parent = (body.get("parent_code") or "").strip() or None
        if new_parent != a.parent_code:
            if new_parent == a.code:
                raise HTTPException(400, "上级科目不能是自身")
            if new_parent and new_parent.startswith(a.code):
                raise HTTPException(400, "上级科目不能是自身的下级")
            parent = L.account_by_code(db, new_parent) if new_parent else None
            if new_parent and not parent:
                raise HTTPException(400, f"上级科目不存在：{new_parent}")
            old_parent = L.account_by_code(db, a.parent_code) if a.parent_code else None
            a.parent_code = new_parent
            a.level = (parent.level + 1) if parent else 1
            if old_parent and not db.query(Account).filter(
                    Account.parent_code == old_parent.code).count():
                old_parent.is_leaf = 1
            if parent:
                parent.is_leaf = 0
            for child in db.query(Account).filter(Account.parent_code == a.code).all():
                child.level = a.level + 1
    _apply_fields(a, body, db)
    db.commit()
    return {"ok": True}


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    a = db.query(Account).get(account_id)
    if not a:
        raise HTTPException(404, "科目不存在")
    used = db.query(VoucherEntry).filter(VoucherEntry.account_id == account_id).count()
    if used:
        raise HTTPException(400, f"科目 {a.code} 已有 {used} 条分录，不能删除")
    if db.query(Account).filter(Account.parent_code == a.code).count():
        raise HTTPException(400, f"科目 {a.code} 存在下级科目，不能删除")
    ob = db.query(OpeningBalance).filter(
        OpeningBalance.account_id == account_id,
        ((OpeningBalance.debit != 0) | (OpeningBalance.credit != 0) |
         (OpeningBalance.quantity != 0))).count()
    if ob:
        raise HTTPException(400, f"科目 {a.code} 已有期初余额，请先在科目期初中清零后再删除，"
                                f"否则会导致试算不平衡")
    # 清理零值期初行/辅助项，避免外键残留
    db.query(OpeningBalanceItem).filter(OpeningBalanceItem.account_id == account_id).delete()
    db.query(OpeningBalance).filter(OpeningBalance.account_id == account_id).delete()
    parent = L.account_by_code(db, a.parent_code) if a.parent_code else None
    db.delete(a)
    db.flush()
    if parent and not db.query(Account).filter(Account.parent_code == parent.code).count():
        parent.is_leaf = 1
    db.commit()
    return {"ok": True}


@router.post("/batch")
def batch_ops(body: dict, db: Session = Depends(get_db)):
    """批量启用/禁用/删除科目"""
    action = body.get("action")
    ids = body.get("ids") or []
    if action not in ("enable", "disable", "delete"):
        raise HTTPException(400, "action 须为 enable/disable/delete")
    if not ids:
        raise HTTPException(400, "未选择科目")
    results = []
    for aid in ids:
        a = db.query(Account).get(aid)
        if not a:
            results.append({"id": aid, "ok": False, "message": "科目不存在"})
            continue
        try:
            if action == "delete":
                used = db.query(VoucherEntry).filter(
                    VoucherEntry.account_id == aid).count()
                if used:
                    raise ValueError(f"已有 {used} 条分录，不能删除")
                if db.query(Account).filter(Account.parent_code == a.code).count():
                    raise ValueError("存在下级科目，不能删除")
                ob = db.query(OpeningBalance).filter(
                    OpeningBalance.account_id == aid,
                    ((OpeningBalance.debit != 0) | (OpeningBalance.credit != 0) |
                     (OpeningBalance.quantity != 0))).count()
                if ob:
                    raise ValueError("有期初余额，请先清零")
                db.query(OpeningBalanceItem).filter(
                    OpeningBalanceItem.account_id == aid).delete()
                db.query(OpeningBalance).filter(
                    OpeningBalance.account_id == aid).delete()
                parent = L.account_by_code(db, a.parent_code) if a.parent_code else None
                code = a.code
                db.delete(a)
                db.flush()
                if parent and not db.query(Account).filter(
                        Account.parent_code == parent.code).count():
                    parent.is_leaf = 1
                results.append({"id": aid, "code": code, "ok": True, "message": "已删除"})
            else:
                a.is_disabled = 1 if action == "disable" else 0
                results.append({"id": aid, "code": a.code, "ok": True,
                                "message": "已禁用" if action == "disable" else "已启用"})
        except ValueError as e:
            results.append({"id": aid, "code": a.code if a else "",
                            "ok": False, "message": str(e)})
    db.commit()
    return {"results": results,
            "ok_count": sum(1 for r in results if r["ok"])}


# ---------- 科目期初（录入/修改） ----------

def _default_opening_year(db: Session) -> str:
    """期初年份：优先取账套设置的期初年份，缺省当前年度"""
    y = L.get_setting(db, "opening_year", "")
    return y if (y and y.isdigit()) else datetime.now().strftime("%Y")


@router.get("/openings/years")
def opening_years(db: Session = Depends(get_db)):
    """期初年份设置 + 已有期初数据的年份列表"""
    years = sorted({r[0] for r in db.query(OpeningBalance.year).distinct().all()})
    return {
        "opening_year": _default_opening_year(db),
        "configured": L.get_setting(db, "opening_year", ""),
        "years": years,
    }


@router.post("/openings/set-year")
@router.put("/openings/set-year")
def set_opening_year(body: dict, db: Session = Depends(get_db)):
    """设置科目期初年份（建账年份）"""
    year = str(body.get("year") or "").strip()
    if not (year.isdigit() and len(year) == 4 and 1990 <= int(year) <= 2999):
        raise HTTPException(400, "年份格式应为 YYYY（1990~2999）")
    s = db.query(Setting).filter(Setting.key == "opening_year").first()
    if not s:
        s = Setting(key="opening_year")
        db.add(s)
    s.value = year
    db.commit()
    return {"ok": True, "opening_year": year}


@router.get("/openings/list")
def list_openings(year: str = None, db: Session = Depends(get_db)):
    year = str(year or "").strip() or _default_opening_year(db)
    obs = {o.account_id: o for o in db.query(OpeningBalance).filter(OpeningBalance.year == year).all()}
    rows = []
    td = tc = 0.0
    # 末级科目 + 历史上已录入期初的非末级科目（可修改/清零，避免脏数据无法修正）
    accounts = [a for a in db.query(Account).filter(Account.is_leaf == 1).order_by(Account.code).all()]
    for a in db.query(Account).filter(Account.is_leaf == 0).order_by(Account.code).all():
        if a.id in obs:
            accounts.append(a)
    for a in accounts:
        o = obs.get(a.id)
        d = L.r2(o.debit) if o else 0.0
        c = L.r2(o.credit) if o else 0.0
        td, tc = L.r2(td + d), L.r2(tc + c)
        rows.append({"account_id": a.id, "code": a.code, "name": a.name,
                     "direction": a.direction, "debit": d, "credit": c,
                     "is_leaf": bool(a.is_leaf),
                     "currency": (o.currency if o else a.currency) or "CNY",
                     "orig_amount": L.r2(o.orig_amount) if o else 0.0,
                     "ytd_debit": L.r2(o.ytd_debit) if o else 0.0,
                     "ytd_credit": L.r2(o.ytd_credit) if o else 0.0,
                     "quantity": o.quantity if o else 0})
    return {"year": year, "rows": rows, "total_debit": td, "total_credit": tc,
            "balanced": abs(td - tc) < 0.005,
            "opening_year": _default_opening_year(db),
            "years": sorted({r[0] for r in db.query(OpeningBalance.year).distinct().all()} | {year})}


@router.put("/openings/save")
def save_openings(body: dict, db: Session = Depends(get_db)):
    """保存/修改期初余额。

    - 同一科目在提交中重复出现时报错，防止金额错位。
    - 逐行校验借贷互斥、非负、两位小数。
    - 保存后按“全年合并口径”校验试算平衡（而非仅本次提交行），
      防止分批修改后全年期初不平。
    """
    year = str(body.get("year") or "").strip() or _default_opening_year(db)
    if not year.isdigit():
        raise HTTPException(400, "年份无效")
    rows = body.get("rows") or []
    seen = set()
    for r in rows:
        aid = r.get("account_id")
        if aid in seen:
            raise HTTPException(400, f"提交的期初行中存在重复科目（account_id={aid}），请合并后再保存")
        seen.add(aid)
        acc = db.query(Account).get(aid)
        if not acc:
            continue
        existed = db.query(OpeningBalance).filter(
            OpeningBalance.account_id == aid, OpeningBalance.year == year).first()
        if not acc.is_leaf and not existed:
            raise HTTPException(400, f"科目 {acc.code} 不是末级科目，不能录入期初")
        d = L.r2(r.get("debit", 0) or 0)
        c = L.r2(r.get("credit", 0) or 0)
        if d < 0 or c < 0:
            raise HTTPException(400, f"科目 {acc.code} 期初金额不能为负")
        if d and c:
            raise HTTPException(400, f"科目 {acc.code} 期初借贷不能同时有值")
        if abs(float(r.get("debit", 0) or 0) - d) > 1e-9 or abs(float(r.get("credit", 0) or 0) - c) > 1e-9:
            raise HTTPException(400, f"科目 {acc.code} 期初金额最多两位小数")
        o = existed
        if not o:
            o = OpeningBalance(account_id=aid, year=year)
            db.add(o)
        o.debit, o.credit, o.quantity = d, c, r.get("quantity", 0) or 0
        if r.get("orig_amount") is not None:
            o.orig_amount = L.r2(r.get("orig_amount") or 0)
        if r.get("currency"):
            o.currency = str(r["currency"])
    db.flush()
    # 全年合并口径校验试算平衡
    total_d = total_c = 0.0
    for o in db.query(OpeningBalance).filter(OpeningBalance.year == year).all():
        total_d, total_c = L.r2(total_d + (o.debit or 0)), L.r2(total_c + (o.credit or 0))
    if abs(total_d - total_c) >= 0.005:
        db.rollback()
        raise HTTPException(
            400, f"期初试算不平衡：借方 {total_d:.2f} ≠ 贷方 {total_c:.2f}（含该年度已有期初），不能保存")
    db.commit()
    return {"ok": True, "total_debit": total_d, "total_credit": total_c}


# ---------- 科目表 / 科目期初 导入导出 ----------

def _stream(buf, filename):
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export.xlsx")
def export_accounts(db: Session = Depends(get_db)):
    """导出科目表（科目编码 科目名称 方向 默认币种 数量核算 计量单位 项目 客户 供应商 部门 员工 存货）"""
    return _stream(X.export_accounts(db), "accounts.xlsx")


@router.post("/import")
async def import_accounts(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        res = X.import_accounts(db, data)
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


@router.get("/openings/export.xlsx")
def export_openings(year: str, db: Session = Depends(get_db)):
    return _stream(X.export_openings(db, year), f"account_openings_{year}.xlsx")


@router.post("/openings/import")
async def import_openings(file: UploadFile = File(...), year: str = "",
                          db: Session = Depends(get_db)):
    data = await file.read()
    try:
        res = X.import_openings(db, year, data)
        db.commit()
        return res
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))


# ---------- 数据清零 ----------

@router.post("/data/clear")
def clear_data(body: dict, db: Session = Depends(get_db)):
    """数据清零：清空凭证/结转记录/会计期间/期初余额（科目表与设置保留）"""
    if not body.get("confirm"):
        raise HTTPException(400, "请勾选确认后再执行数据清零")
    scope = body.get("scope") or ["vouchers", "carryover", "periods", "openings"]
    cleared = {}
    # 删除顺序考虑外键：结转记录 → 凭证分录 → 凭证
    if "carryover" in scope:
        cleared["carryover_records"] = db.query(CarryoverRecord).delete(synchronize_session=False)
    if "vouchers" in scope:
        cleared["voucher_entries"] = db.query(VoucherEntry).delete(synchronize_session=False)
        cleared["vouchers"] = db.query(Voucher).delete(synchronize_session=False)
    if "periods" in scope:
        cleared["periods"] = db.query(Period).delete(synchronize_session=False)
    if "openings" in scope:
        cleared["opening_items"] = db.query(OpeningBalanceItem).delete(synchronize_session=False)
        cleared["opening_balances"] = db.query(OpeningBalance).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "cleared": cleared}
