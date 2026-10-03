"""明细账导入 / 导出

明细账文件格式（与主流财务软件导出的明细账一致）：

    序号 科目编码 科目 日期 凭证号 摘要 借方 贷方 方向 余额
    1    1001    库存现金 2021-01 期初余额            平
    2    1001    库存现金 2022-07-31 记-001 日常办公… 38.90 贷 38.90

规则：
- 期初行：凭证号/摘要含“期初/年初/上年结转”，或日期只到年月（YYYY-MM）、或日期为空；
  记入科目期初余额，年份取日期年份（缺省用 opening_year 参数 / 账套期初年份设置）。
- 记账行：按（日期, 原凭证号）合并为一张凭证；借贷平衡 → 正式凭证，
  不平衡（例如只导入了单个科目的明细）→ 草稿凭证并在结果中提示，便于补齐对方科目后再导。
- 重复导入同一文件幂等：与已有凭证分录完全相同的行自动跳过；
  同一凭证号再次导入不同科目行时，会并入原凭证（补齐对方科目后自动转正式）。
- 科目不存在时按“科目编码/科目”自动创建（末级），并在结果中列出。
"""
import io
import re
from datetime import datetime, date as _date

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from ..models import Account, OpeningBalance, Setting, Voucher, VoucherEntry
from . import ledger as L
from . import vouchers as V
from .excel_io import _style_header, _autosize, MONEY_FMT

DETAIL_HEADERS = ["序号", "科目编码", "科目", "日期", "凭证号", "摘要",
                  "借方", "贷方", "方向", "余额"]

# 表头别名 → 标准列名
COLUMN_ALIASES = {
    "序号": ["序号", "行号", "no", "No"],
    "科目编码": ["科目编码", "科目代码", "编码", "科目编号"],
    "科目": ["科目", "科目名称", "账户", "账户名称"],
    "日期": ["日期", "记账日期", "业务日期"],
    "凭证号": ["凭证号", "凭证编号", "凭证字", "凭证"],
    "摘要": ["摘要", "说明", "备注"],
    "借方": ["借方", "借方金额", "借方发生额", "借方发生", "借"],
    "贷方": ["贷方", "贷方金额", "贷方发生额", "贷方发生", "贷"],
    "方向": ["方向", "余额方向"],
    "余额": ["余额", "期末余额", "结余"],
}

_OPENING_MARKS = ("期初", "年初", "上年结转", "结转下年", "本年累计", "累计")
_DATE_FULL = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_DATE_MONTH = re.compile(r"^\d{4}-\d{1,2}$")


# ---------------- 通用工具 ----------------

def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (_date, datetime)):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def _num(v, default=0.0, allow_negative: bool = False) -> float:
    if v in (None, ""):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("，", "")
    if not s:
        return default
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    if neg and not allow_negative:
        raise ValueError(f"金额不能为负：{v}")
    if neg:
        s = s.strip("()").lstrip("-") or "0"
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        raise ValueError(f"数字格式无效：{v}")


def _norm_date(v) -> str:
    """日期规范化：datetime / YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD / YYYY-MM"""
    s = _text(v)
    if not s:
        return ""
    if isinstance(v, (_date, datetime)):
        return v.strftime("%Y-%m-%d")
    s = s.replace("/", "-").replace(".", "-")
    if re.match(r"^\d{8}$", s):
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if _DATE_FULL.match(s):
        y, m, d = s.split("-")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    if _DATE_MONTH.match(s):
        y, m = s.split("-")
        return f"{int(y):04d}-{int(m):02d}"
    return s


def _dir_of(net: float) -> str:
    if abs(net) < 0.005:
        return "平"
    return "借" if net > 0 else "贷"


def _read_rows(data: bytes) -> list:
    """读取 xlsx / csv / tsv 明细账文件为二维列表"""
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    except Exception:
        pass
    text = None
    for enc in ("utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("无法解析文件（支持 .xlsx / .csv / .txt）")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("文件内容为空")
    delim = "\t" if lines[0].count("\t") >= lines[0].count(",") else ","
    rows = []
    for ln in lines:
        if delim == "\t":
            rows.append([c.strip() for c in ln.split("\t")])
        else:
            import csv as _csv
            rows.append(next(_csv.reader([ln])))
    return rows


def _header_map(rows: list):
    """识别表头行，返回 (列名→下标, 数据起始行下标)；识别不到按默认列序"""
    alias = {}
    for canon, names in COLUMN_ALIASES.items():
        for n in names:
            alias[n.strip().lower()] = canon
    for i, row in enumerate(rows[:5]):
        mapping = {}
        for j, cell in enumerate(row or []):
            key = alias.get(_text(cell).lower())
            if key and key not in mapping:
                mapping[key] = j
        if len(mapping) >= 3 and "科目编码" in mapping and "日期" in mapping:
            return mapping, i + 1
    return {name: i for i, name in enumerate(DETAIL_HEADERS)}, 0


# ---------------- 导出 ----------------

def _row_cells(mapping: dict, row: list):
    return {name: (row[idx] if idx is not None and idx < len(row) else None)
            for name, idx in mapping.items()}


def export_detail_ledger(db: Session, account_code: str = None,
                         from_period: str = None, to_period: str = None) -> io.BytesIO:
    """导出明细账（序号 科目编码 科目 日期 凭证号 摘要 借方 贷方 方向 余额）"""
    from_period = from_period or f"{to_period[:4]}-01"
    to_period = to_period or from_period
    if account_code:
        ids = L.account_ids_for(db, account_code, rollup=True)
        accounts = db.query(Account).filter(Account.id.in_(ids)).order_by(Account.code).all() if ids else []
    else:
        accounts = db.query(Account).order_by(Account.code).all()
    acc_map = {a.id: a for a in db.query(Account).all()}
    out_rows = []
    seq = 0
    for a in accounts:
        entries = db.query(VoucherEntry, Voucher).join(
            Voucher, Voucher.id == VoucherEntry.voucher_id
        ).filter(
            VoucherEntry.account_id == a.id, Voucher.status == "posted",
            Voucher.period >= from_period, Voucher.period <= to_period,
        ).order_by(Voucher.date, Voucher.voucher_no, VoucherEntry.line_no).all()
        od, oc = L.opening_sums(db, [a.id], from_period)
        if not entries and abs(od - oc) < 0.005 and not account_code:
            continue  # 全量导出时跳过无发生额且无期初的科目
        anchor = L.account_opening_anchor(db, a.id, from_period) or from_period[:4]
        odn, ocn = L.net_side(od, oc)  # 期初按余额口径单边列示
        net = r2f(od - oc)
        seq += 1
        out_rows.append([seq, a.code, a.name, f"{anchor}-01", "期初余额", "",
                         odn or None, ocn or None, _dir_of(net), abs(net) or None])
        for e, v in entries:
            net = r2f(net + (e.debit or 0) - (e.credit or 0))
            seq += 1
            out_rows.append([seq, a.code, a.name, v.date,
                             (v.source_no or v.voucher_no), e.summary or "",
                             e.debit or None, e.credit or None,
                             _dir_of(net), abs(net) or None])
    wb = Workbook()
    ws = wb.active
    ws.title = "明细账"
    ws.append(DETAIL_HEADERS)
    _style_header(ws)
    for r in out_rows:
        ws.append(r)
    for idx in (6, 7, 9):  # 借方 贷方 余额（1 基列 7/8/10）
        for row in ws.iter_rows(min_row=2, min_col=idx + 1, max_col=idx + 1):
            for c in row:
                if c.value is not None:
                    c.number_format = MONEY_FMT
    _autosize(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def r2f(x) -> float:
    return L.r2(x)


def detail_ledger_template() -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "明细账导入模板"
    ws.append(DETAIL_HEADERS)
    _style_header(ws)
    ws.append([1, "1001", "库存现金", "2021-01", "期初余额", "", None, None, "平", None])
    ws.append([2, "1001", "库存现金", "2021-01-31", "记-001", "提现备用金", 5000.00,
               None, "借", 5000.00])
    ws.append([3, "1001", "库存现金", "2021-01-31", "记-002", "购买办公用品", None,
               300.00, "贷", 4700.00])
    ws.append([4, "1002", "银行存款", "2021-01", "期初余额", "", 10000.00, None, "借", 10000.00])
    ws.append([5, "1002", "银行存款", "2021-01-31", "记-001", "提现备用金", None,
               5000.00, "贷", 5000.00])
    ws.append([6, "3001", "实收资本", "2021-01", "期初余额", "", None, 10000.00, "贷", 10000.00])
    ws.append([7, "5602", "管理费用", "2021-01", "期初余额", "", None, None, "平", None])
    ws.append([8, "5602", "管理费用", "2021-01-31", "记-002", "购买办公用品", 300.00,
               None, "借", 300.00])
    _autosize(ws)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ---------------- 导入 ----------------

def _is_opening_row(no: str, summary: str, date_raw: str) -> bool:
    mark = f"{no}{summary}"
    # 有真实凭证号的行永远是记账行（避免摘要含“累计/期初”等字样的正常凭证被当成期初行）
    has_voucher_no = bool(no) and not any(k in no for k in _OPENING_MARKS)
    if has_voucher_no:
        return False
    if any(k in mark for k in _OPENING_MARKS):
        return True
    if not date_raw:
        return not no  # 无日期也无凭证号 → 按期初行处理
    return bool(_DATE_MONTH.match(date_raw))


def _vtype_of(orig_no: str, default: str = "记") -> str:
    m = re.match(r"^([A-Za-z\u4e00-\u9fa5]{1,6})[-—_]", orig_no or "")
    return m.group(1) if m else default


def _ensure_account(db: Session, code: str, name: str, created: list) -> Account:
    acc = L.account_by_code(db, code)
    if acc:
        return acc
    parent_code = None
    for plen in range(len(code) - 1, 0, -1):
        if L.account_by_code(db, code[:plen]):
            parent_code = code[:plen]
            break
    parent = L.account_by_code(db, parent_code) if parent_code else None
    direction = "C" if code[:1] in ("2", "3") or L.infer_category(code, "D") == "income" else "D"
    acc = Account(
        code=code, name=(name or code).strip()[:100], parent_code=parent_code,
        direction=direction, category=L.infer_category(code, direction),
        is_leaf=1, level=(parent.level + 1) if parent else 1,
    )
    db.add(acc)
    if parent:
        parent.is_leaf = 0
    db.flush()
    V.sync_account_cashflow_map(db, [acc.id])  # 新科目现金流量对照随科目表同步
    created.append(f"{code} {acc.name}")
    return acc


def _line_key(entry: dict):
    return (entry["account_id"], (entry.get("summary") or "").strip()[:200],
            L.r2(entry.get("debit", 0) or 0), L.r2(entry.get("credit", 0) or 0))


def _find_voucher(db: Session, date: str, orig_no: str):
    return db.query(Voucher).filter(
        Voucher.date == date,
        ((Voucher.source_no == orig_no) | (Voucher.voucher_no == orig_no)),
    ).first()


def _voucher_lines(v: Voucher):
    return [_line_key({"account_id": e.account_id, "summary": e.summary,
                       "debit": e.debit, "credit": e.credit}) for e in v.entries]


def _restatus(v: Voucher):
    total_d = L.r2(sum(e.debit for e in v.entries))
    total_c = L.r2(sum(e.credit for e in v.entries))
    balanced = abs(total_d - total_c) < 0.005
    if balanced and v.status == "draft":
        v.status = "posted"
        v.posted_at = V.now_str()
    elif not balanced:
        v.status = "draft"
    return total_d, total_c, balanced


def import_detail_ledger(db: Session, data: bytes, opening_year: str = None) -> dict:
    rows = _read_rows(data)
    mapping, start = _header_map(rows)
    errors, warnings = [], []
    created_accounts = []
    red_rows = 0
    opening_acc = {}      # (account_id, year) -> {"debit":, "credit":}
    run_net = {}          # account_id -> 按文件行序累计的净额（借正贷负），用于余额列核对
    opening_rows = 0
    groups = {}           # (date, orig_no) -> {"lines": [...], "rows": [...]}
    total_rows = 0

    for i in range(start, len(rows)):
        row = rows[i]
        if not row or all(_text(c) == "" for c in row):
            continue
        cells = _row_cells(mapping, row)
        code = _text(cells.get("科目编码"))
        name = _text(cells.get("科目"))
        date_raw = _norm_date(cells.get("日期"))
        orig_no = _text(cells.get("凭证号"))
        summary = _text(cells.get("摘要"))
        if not code and not date_raw and not orig_no and not summary:
            continue
        total_rows += 1
        if _text(cells.get("科目编码")).lower() == "科目编码":
            continue  # 重复表头
        if not code:
            errors.append(f"第{i + 1}行：科目编码为空")
            continue
        if not re.match(r"^\d{3,20}$", code):
            errors.append(f"第{i + 1}行：科目编码无效（应为数字编码）：{code}")
            continue
        try:
            debit = _num(cells.get("借方"), allow_negative=True)
            credit = _num(cells.get("贷方"), allow_negative=True)
            balance_raw = cells.get("余额")
            balance = _num(balance_raw, default=None, allow_negative=True) \
                if balance_raw not in (None, "") else None
        except ValueError as e:
            errors.append(f"第{i + 1}行：{e}")
            continue
        if debit < 0 or credit < 0:
            red_rows += 1  # 红字（负数）金额原样入库
        direction = _text(cells.get("方向"))

        # ---------- 期初行 ----------
        if _is_opening_row(orig_no, summary, date_raw):
            year = date_raw[:4] if date_raw else ""
            if not (year.isdigit() and len(year) == 4):
                year = str(opening_year or L.get_setting(db, "opening_year", ""))[:4]
            if not (year and year.isdigit()):
                errors.append(f"第{i + 1}行：期初行无法确定年份（请填日期如 2021-01 或指定期初年份）")
                continue
            if debit and credit:
                # 借贷同时有值：按净额处理（其它平台可能导出累计发生额口径的期初）
                net_amt = L.r2(debit - credit)
                amount, side = (net_amt, "D") if net_amt >= 0 else (-net_amt, "C")
                warnings.append(
                    f"第{i + 1}行：期初借贷同时有值，已按净额 {net_amt:.2f} 处理")
            elif debit or credit:
                amount, side = (debit, "D") if debit else (credit, "C")
            elif balance and direction in ("借", "贷"):
                amount, side = balance, ("D" if direction == "借" else "C")
            elif balance:
                errors.append(f"第{i + 1}行：期初行有余额但缺少方向（借/贷）")
                continue
            else:
                amount, side = 0.0, "D"
            try:
                acc = _ensure_account(db, code, name, created_accounts)
            except Exception as e:  # pragma: no cover - 防御
                errors.append(f"第{i + 1}行：科目 {code} 创建失败：{e}")
                continue
            key = (acc.id, year)
            slot = opening_acc.setdefault(key, {"debit": 0.0, "credit": 0.0})
            if side == "D":
                slot["debit"] = L.r2(slot["debit"] + amount)
            else:
                slot["credit"] = L.r2(slot["credit"] + amount)
            run_net[acc.id] = L.r2(amount if side == "D" else -amount)
            opening_rows += 1
            if balance is not None and abs(balance - amount) > 0.01:
                warnings.append(f"第{i + 1}行：期初余额列 {balance:.2f} 与借贷金额 {amount:.2f} 不一致，以借贷金额为准")
            continue

        # ---------- 记账行 ----------
        if not date_raw or not _DATE_FULL.match(date_raw):
            errors.append(f"第{i + 1}行：日期无效（应为 YYYY-MM-DD）：{date_raw or '空'}")
            continue
        if not L.valid_period(date_raw[:7]):
            errors.append(f"第{i + 1}行：日期无效：{date_raw}")
            continue
        if not orig_no:
            errors.append(f"第{i + 1}行：凭证号为空")
            continue
        if debit and credit:
            errors.append(f"第{i + 1}行：借方与贷方金额不能同时有值")
            continue
        if not debit and not credit:
            errors.append(f"第{i + 1}行：借贷方金额不能同时为零")
            continue
        try:
            acc = _ensure_account(db, code, name, created_accounts)
        except Exception as e:  # pragma: no cover - 防御
            errors.append(f"第{i + 1}行：科目 {code} 创建失败：{e}")
            continue
        g = groups.setdefault((date_raw, orig_no),
                              {"lines": [], "rows": [], "vtype": _vtype_of(orig_no)})
        g["lines"].append({"account_id": acc.id, "summary": summary or "",
                           "debit": L.r2(debit), "credit": L.r2(credit), "row": i + 1})
        g["rows"].append(i + 1)
        # 余额列核对（文件自带的滚动余额与发生额累计比对）
        net = L.r2(run_net.get(acc.id, 0.0) + debit - credit)
        run_net[acc.id] = net
        if balance is not None and abs(abs(net) - abs(balance)) > 0.01:
            warnings.append(f"第{i + 1}行：科目 {code} 余额不符（文件 {balance:.2f}，按发生额累计 {abs(net):.2f}）")
        if direction in ("借", "贷", "平") and _dir_of(net) != direction:
            warnings.append(f"第{i + 1}行：科目 {code} 余额方向不符（文件 {direction}，计算 {_dir_of(net)}）")

    # ---------- 期初写入 ----------
    opening_years = sorted({y for _aid, y in opening_acc})
    for (aid, year), slot in opening_acc.items():
        o = db.query(OpeningBalance).filter(
            OpeningBalance.account_id == aid, OpeningBalance.year == year).first()
        if not o:
            o = OpeningBalance(account_id=aid, year=year)
            db.add(o)
        o.debit, o.credit = L.r2(slot["debit"]), L.r2(slot["credit"])
    db.flush()
    total_od = total_oc = 0.0
    for slot in opening_acc.values():
        total_od, total_oc = L.r2(total_od + slot["debit"]), L.r2(total_oc + slot["credit"])

    # ---------- 期初年份设置 ----------
    opening_year_updated = ""
    if opening_years:
        target = opening_years[0]
        current = L.get_setting(db, "opening_year", "")
        if current != target:
            s = db.query(Setting).filter(Setting.key == "opening_year").first()
            if not s:
                s = Setting(key="opening_year")
                db.add(s)
            s.value = target
            opening_year_updated = target
        if len(opening_years) > 1:
            warnings.append(f"文件含多个期初年份：{'、'.join(opening_years)}，期初年份设置取最早 {target}")

    # ---------- 凭证生成 ----------
    created_vouchers = merged_vouchers = skipped_vouchers = draft_vouchers = 0
    unbalanced = []
    for (date, orig_no), g in sorted(groups.items()):
        lines = g["lines"]
        period = date[:7]
        existing = _find_voucher(db, date, orig_no)
        if existing:
            have = _voucher_lines(existing)
            need = []
            pool = list(have)
            for ln in lines:
                k = _line_key(ln)
                if k in pool:
                    pool.remove(k)
                else:
                    need.append(ln)
            if not need:
                skipped_vouchers += 1
                continue
            if V.is_period_closed(db, period):
                errors.append(f"凭证 {orig_no}（{date}）：会计期间 {period} 已结账，不能追加分录")
                continue
            max_line = max([e.line_no for e in existing.entries] or [0])
            for j, ln in enumerate(need, 1):
                existing.entries.append(VoucherEntry(
                    line_no=max_line + j, account_id=ln["account_id"],
                    summary=(ln["summary"] or "")[:200],
                    debit=ln["debit"], credit=ln["credit"],
                ))
            total_d, total_c, balanced = _restatus(existing)
            merged_vouchers += 1
            if not balanced:
                draft_vouchers += 1
                unbalanced.append({"voucher_no": orig_no, "date": date,
                                   "debit": total_d, "credit": total_c,
                                   "difference": L.r2(total_d - total_c)})
            continue
        entries = [{"account_id": ln["account_id"], "summary": ln["summary"],
                    "debit": ln["debit"], "credit": ln["credit"]} for ln in lines]
        total_d = L.r2(sum(e["debit"] for e in entries))
        total_c = L.r2(sum(e["credit"] for e in entries))
        balanced = abs(total_d - total_c) < 0.005
        try:
            v = V.create_voucher(
                db, date=date, vtype=g["vtype"], entries=entries,
                status="posted" if balanced else "draft", source="import",
                source_no=orig_no, require_balance=balanced, allow_nonleaf=True,
                remark="明细账导入",
            )
        except ValueError as e:
            errors.append(f"凭证 {orig_no}（{date}）：{e}")
            continue
        created_vouchers += 1
        if not balanced:
            draft_vouchers += 1
            unbalanced.append({"voucher_no": orig_no, "date": date,
                               "debit": total_d, "credit": total_c,
                               "difference": L.r2(total_d - total_c)})

    if total_rows == 0:
        raise ValueError("导入失败：文件中没有可识别的明细账数据行")
    if errors and created_vouchers == 0 and merged_vouchers == 0 and opening_rows == 0:
        raise ValueError("导入失败：" + "；".join(errors[:10]))
    # 识别结转类凭证并登记结转（与凭证导入同口径）；可重复执行（幂等）
    from . import carryover as C
    sweep = C.sweep_carryover(db)
    if abs(total_od - total_oc) >= 0.005 and opening_rows:
        warnings.append(
            f"期初试算不平衡：借方 {total_od:.2f} ≠ 贷方 {total_oc:.2f}（可能只导入了部分科目）")
    for u in unbalanced:
        warnings.append(
            f"凭证 {u['voucher_no']}（{u['date']}）借贷不平：借 {u['debit']:.2f} / 贷 {u['credit']:.2f}，"
            f"已生成草稿凭证，补齐对方科目后再导入即可自动转正式")
    return {
        "rows": total_rows,
        "created_vouchers": created_vouchers,
        "merged_vouchers": merged_vouchers,
        "skipped_vouchers": skipped_vouchers,
        "draft_vouchers": draft_vouchers,
        "unbalanced": unbalanced,
        "opening_rows": opening_rows,
        "opening_years": opening_years,
        "opening_year": opening_years[0] if opening_years else "",
        "opening_year_updated": opening_year_updated,
        "opening_total_debit": total_od,
        "opening_total_credit": total_oc,
        "opening_balanced": abs(total_od - total_oc) < 0.005,
        "created_accounts": created_accounts,
        "red_rows": red_rows,
        "carryover_marked": sweep["marked"],
        "carryover_records": sweep["records"],
        "errors": errors,
        "warnings": warnings,
    }
