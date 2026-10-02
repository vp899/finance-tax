"""数据库连接与初始化（支持多账套）

账套（book set）= 一套独立的账务数据（科目/凭证/期初/设置…），各自使用独立的 SQLite 文件：
- 默认账套 id=default → data/finance.db（与历史版本保持一致）
- 其它账套          → data/books/<book_id>.db
账套注册表          → data/books.json

请求选账套的方式（优先级从高到低）：
1. 请求头 X-Book-Id
2. 查询参数 book_id
3. 缺省 → 默认账套
"""
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "finance.db")          # 默认账套数据库
BOOKS_DIR = os.path.join(DATA_DIR, "books")             # 其它账套数据库目录
REGISTRY_PATH = os.path.join(DATA_DIR, "books.json")    # 账套注册表
DEFAULT_BOOK_ID = "default"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_BOOK_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")


# ---------------- 账套注册表 ----------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_registry() -> dict:
    return {
        "default": DEFAULT_BOOK_ID,
        "books": [{
            "id": DEFAULT_BOOK_ID,
            "name": "默认账套",
            "remark": "",
            "file": "finance.db",
            "created_at": _now(),
        }],
    }


def read_registry() -> dict:
    if not os.path.exists(REGISTRY_PATH):
        reg = _default_registry()
        write_registry(reg)
        return reg
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            reg = json.load(f)
    except Exception:
        reg = _default_registry()
    books = reg.get("books") or []
    if not any(b.get("id") == DEFAULT_BOOK_ID for b in books):
        books.insert(0, _default_registry()["books"][0])
        reg["books"] = books
    if not reg.get("default"):
        reg["default"] = DEFAULT_BOOK_ID
    return reg


def write_registry(reg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    shutil.move(tmp, REGISTRY_PATH)


def list_books() -> list:
    reg = read_registry()
    default_id = reg.get("default") or DEFAULT_BOOK_ID
    out = []
    for b in reg["books"]:
        d = dict(b)
        d["is_default"] = b["id"] == default_id
        out.append(d)
    return out


def get_book(book_id: str) -> dict:
    for b in read_registry()["books"]:
        if b["id"] == book_id:
            return b
    return None


def book_db_path(book_id: str) -> str:
    if book_id == DEFAULT_BOOK_ID:
        return DB_PATH
    b = get_book(book_id)
    if not b:
        raise KeyError(f"账套不存在：{book_id}")
    return os.path.join(DATA_DIR, b.get("file") or f"books/{book_id}.db")


def valid_book_id(book_id: str) -> bool:
    return bool(book_id) and bool(_BOOK_ID_RE.match(book_id))


def create_book(name: str, remark: str = "", copy_from: str = None,
                book_id: str = None) -> dict:
    """新建账套：初始化空账套（含默认科目/设置）或从既有账套复制数据"""
    name = (name or "").strip()
    if not name:
        raise ValueError("账套名称必填")
    reg = read_registry()
    used = {b["id"] for b in reg["books"]}
    bid = (book_id or "").strip()
    if bid:
        if not valid_book_id(bid) or bid in used:
            raise ValueError(f"账套 id 不可用：{bid}（仅限字母/数字/下划线/中划线，且不能重复）")
    else:
        n = len(used) + 1
        while f"book{n:03d}" in used:
            n += 1
        bid = f"book{n:03d}"
    if copy_from and not get_book(copy_from):
        raise ValueError(f"来源账套不存在：{copy_from}")
    os.makedirs(BOOKS_DIR, exist_ok=True)
    path = os.path.join(BOOKS_DIR, f"{bid}.db")
    if os.path.exists(path):
        raise ValueError(f"账套数据库文件已存在：{bid}")
    if copy_from:
        src_path = book_db_path(copy_from)
        if not os.path.exists(src_path):
            raise ValueError(f"来源账套数据文件不存在：{copy_from}")
        src = sqlite3.connect(src_path)
        try:
            dst = sqlite3.connect(path)
            src.backup(dst)
            dst.close()
        finally:
            src.close()
    else:
        sqlite3.connect(path).close()
        _init_book_db(path)
    reg["books"].append({
        "id": bid, "name": name, "remark": (remark or "")[:200],
        "file": f"books/{bid}.db", "created_at": _now(),
    })
    write_registry(reg)
    return {"id": bid, "name": name, "remark": remark or ""}


def update_book(book_id: str, **fields) -> dict:
    reg = read_registry()
    for b in reg["books"]:
        if b["id"] != book_id:
            continue
        if "name" in fields:
            name = (fields.get("name") or "").strip()
            if not name:
                raise ValueError("账套名称必填")
            b["name"] = name
        if "remark" in fields:
            b["remark"] = str(fields.get("remark") or "")[:200]
        write_registry(reg)
        return b
    raise ValueError(f"账套不存在：{book_id}")


def set_default_book(book_id: str):
    if not get_book(book_id):
        raise ValueError(f"账套不存在：{book_id}")
    reg = read_registry()
    reg["default"] = book_id
    write_registry(reg)


def delete_book(book_id: str):
    reg = read_registry()
    if book_id == DEFAULT_BOOK_ID:
        raise ValueError("默认账套不能删除")
    if (reg.get("default") or DEFAULT_BOOK_ID) == book_id:
        raise ValueError("当前默认账套不能删除，请先把其它账套设为默认")
    books = [b for b in reg["books"] if b["id"] != book_id]
    if len(books) == len(reg["books"]):
        raise ValueError(f"账套不存在：{book_id}")
    reg["books"] = books
    write_registry(reg)
    dispose_engine(book_id)
    if book_id != DEFAULT_BOOK_ID:
        path = os.path.join(BOOKS_DIR, f"{book_id}.db")
        for suffix in ("", "-wal", "-shm"):
            p = path + suffix
            if os.path.exists(p):
                os.remove(p)


# ---------------- 引擎 / 会话 ----------------

_engines = {}


def book_engine(book_id: str):
    if book_id == DEFAULT_BOOK_ID:
        return engine
    eng = _engines.get(book_id)
    if eng is not None:
        return eng
    path = book_db_path(book_id)
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _pragma(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    _engines[book_id] = eng
    return eng


def dispose_engine(book_id: str):
    if book_id == DEFAULT_BOOK_ID:
        return
    eng = _engines.pop(book_id, None)
    if eng is not None:
        eng.dispose()


def _init_book_db(path: str):
    """对指定库文件建表 + 迁移 + 种子数据"""
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    try:
        Base.metadata.create_all(bind=eng)
        ensure_schema(path)
        from .seed import ensure_seed
        ensure_seed(bind=eng)
    finally:
        eng.dispose()


def ensure_schema(db_path: str = None):
    """轻量迁移：为已有库补齐新增列（SQLite 不支持加约束，只补列）"""
    db_path = db_path or DB_PATH
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        add_columns = {
            "accounts": [
                ("is_disabled", "INTEGER DEFAULT 0"),
                ("quantity_accounting", "INTEGER DEFAULT 0"),
                ("aux_project", "INTEGER DEFAULT 0"),
                ("aux_customer", "INTEGER DEFAULT 0"),
                ("aux_supplier", "INTEGER DEFAULT 0"),
                ("aux_dept", "INTEGER DEFAULT 0"),
                ("aux_employee", "INTEGER DEFAULT 0"),
                ("aux_inventory", "INTEGER DEFAULT 0"),
            ],
            "opening_balances": [
                ("currency", "VARCHAR(10) DEFAULT 'CNY'"),
                ("orig_amount", "FLOAT DEFAULT 0"),
                ("ytd_debit", "FLOAT DEFAULT 0"),
                ("ytd_credit", "FLOAT DEFAULT 0"),
                ("ytd_debit_qty", "FLOAT DEFAULT 0"),
                ("ytd_credit_qty", "FLOAT DEFAULT 0"),
                ("ytd_debit_orig", "FLOAT DEFAULT 0"),
                ("ytd_credit_orig", "FLOAT DEFAULT 0"),
            ],
            "vouchers": [
                ("source_no", "VARCHAR(30) DEFAULT ''"),
                ("maker", "VARCHAR(50) DEFAULT ''"),
                ("reviewer", "VARCHAR(50) DEFAULT ''"),
            ],
            "voucher_entries": [
                ("spec", "VARCHAR(100) DEFAULT ''"),
                ("price", "FLOAT DEFAULT 0"),
                ("orig_amount", "FLOAT DEFAULT 0"),
                ("aux_json", "TEXT DEFAULT ''"),
            ],
        }
        for table, cols in add_columns.items():
            existing = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            if not existing:
                continue
            for name, ddl in cols:
                if name not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        conn.commit()
    finally:
        conn.close()


def ensure_books():
    """启动时初始化账套注册表与各账套库结构"""
    os.makedirs(BOOKS_DIR, exist_ok=True)
    read_registry()
    Base.metadata.create_all(bind=engine)
    ensure_schema(DB_PATH)
    for b in read_registry()["books"]:
        if b["id"] == DEFAULT_BOOK_ID:
            continue
        path = book_db_path(b["id"])
        if os.path.exists(path):
            _init_book_db(path)


def get_book_id(request: Request = None) -> str:
    """解析当前请求的账套 id（请求头 X-Book-Id > 查询参数 book_id > 默认账套）"""
    book_id = None
    if request is not None:
        headers = getattr(request, "headers", None)
        query = getattr(request, "query_params", None)
        book_id = (headers.get("X-Book-Id") if headers is not None else None) \
            or (query.get("book_id") if query is not None else None)
    book_id = (book_id or "").strip() or read_registry().get("default") or DEFAULT_BOOK_ID
    if not valid_book_id(book_id) or not get_book(book_id):
        raise KeyError(f"账套不存在：{book_id}")
    return book_id


def get_db(request: Request = None):
    """FastAPI 依赖：按当前账套返回数据库会话"""
    from fastapi import HTTPException
    try:
        book_id = get_book_id(request)
    except KeyError as e:
        raise HTTPException(400, str(e))
    if book_id == DEFAULT_BOOK_ID:
        db = SessionLocal()
    else:
        db = sessionmaker(autocommit=False, autoflush=False, bind=book_engine(book_id))()
    try:
        yield db
    finally:
        db.close()
