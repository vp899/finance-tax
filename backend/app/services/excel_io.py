"""Excel 导入导出"""
import io
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from sqlalchemy.orm import Session
from ..models import Account, Voucher, VoucherEntry
from . import ledger as L
from . import vouchers as V

HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
HEADER_FONT = Font(bold=True)
THIN = Border(*[Side(style="thin", color="B0B0B0")] * 4)
MONEY_FMT = "#,##0.00"


def _style_header(ws, row=1):
    for cell in ws[row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        cell.border = THIN


def _autosize(ws, max_width=40):
    for col in ws.columns:
        length = 0
        letter = col[0].column_letter
        for cell in col:
            v = "" if cell.value is None else str(cell.value)
            length = max(length, min(len(v) * 2, max_width))
        ws.column_dimensions[letter].width = max(10, length + 2)


def export_vouchers(db: Session, from_period: str, to_period: str) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "凭证明细"
    headers = ["凭证号", "日期", "期间", "凭证类型", "状态", "行号", "摘要",
               "科目编码", "科目名称", "借方金额", "贷方金额", "数量", "单位", "现金流量项目"]
    ws.append(headers)
    _style_header(ws)
    acc_map = {a.id: a for a in db.query(Account).all()}
    vouchers = db.query(Voucher).filter(
        Voucher.period >= from_period, Voucher.period <= to_period
    ).order_by(Voucher.date, Voucher.voucher_no).all()
    for v in vouchers:
        for e in v.entries:
            a = acc_map[e.account_id]
            ws.append([v.voucher_no, v.date, v.period, v.vtype, v.status, e.line_no,
                       e.summary, a.code, a.name, e.debit, e.credit,
                       e.quantity, e.unit, e.cashflow_code or ""])
    for row in ws.iter_rows(min_row=2, min_col=10, max_col=11):
        for c in row:
            c.number_format = MONEY_FMT
    _autosize(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_table(title: str, headers: list, rows: list, money_cols: list) -> io.BytesIO:
    """通用表导出；rows 为与 headers 对应的值列表"""
    wb = Workbook()
    ws = wb.active
    ws.title = title[:28]
    ws.append(headers)
    _style_header(ws)
    for r in rows:
        ws.append(r)
    for idx in money_cols:
        for row in ws.iter_rows(min_row=2, min_col=idx + 1, max_col=idx + 1):
            for c in row:
                c.number_format = MONEY_FMT
    _autosize(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def voucher_template() -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "凭证导入模板"
    ws.append(["日期(YYYY-MM-DD)", "凭证类型", "摘要", "科目编码", "借方金额", "贷方金额", "数量", "单位"])
    _style_header(ws)
    ws.append(["2026-01-31", "记", "示例：销售商品", "1002", 11300, 0, "", ""])
    ws.append(["2026-01-31", "记", "示例：销售商品", "5001", 0, 10000, "", ""])
    ws.append(["2026-01-31", "记", "示例：销售商品", "222101", 0, 1300, "", ""])
    _autosize(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def import_vouchers(db: Session, data: bytes):
    """导入凭证（同一凭证号/日期+类型+连续行合成一张凭证）"""
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    errors, created = [], 0
    groups = {}
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not row or all(v in (None, "") for v in row):
            continue
        date, vtype, summary, code, debit, credit, qty, unit = (list(row) + [None] * 8)[:8]
        if not date or not code:
            errors.append(f"第{i}行：日期或科目编码为空")
            continue
        date = str(date)[:10]
        if not L.valid_period(date[:7]):
            errors.append(f"第{i}行：日期无效 {date}")
            continue
        key = (date, str(vtype or "记"))
        groups.setdefault(key, []).append({
            "row": i, "summary": str(summary or ""),
            "account_code": str(code).strip(),
            "debit": float(debit or 0), "credit": float(credit or 0),
            "quantity": float(qty or 0), "unit": str(unit or ""),
        })
    for (date, vtype), lines in groups.items():
        entries, ok = [], True
        for ln in lines:
            acc = L.account_by_code(db, ln["account_code"])
            if not acc:
                errors.append(f"第{ln['row']}行：科目 {ln['account_code']} 不存在")
                ok = False
                continue
            entries.append({
                "account_id": acc.id, "summary": ln["summary"],
                "debit": ln["debit"], "credit": ln["credit"],
                "quantity": ln["quantity"], "unit": ln["unit"],
            })
        if not ok:
            continue
        try:
            V.create_voucher(db, date=date, vtype=vtype, entries=entries, source="import")
            created += 1
        except ValueError as e:
            errors.append(f"凭证 {date} {vtype}：{e}")
    if errors and created == 0:
        raise ValueError("导入失败：" + "；".join(errors[:10]))
    return {"created": created, "errors": errors}
