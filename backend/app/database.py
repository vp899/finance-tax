"""数据库连接与初始化"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "finance.db")
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


def ensure_schema():
    """轻量迁移：为已有库补齐新增列（SQLite 不支持加约束，只补列）"""
    import sqlite3
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
