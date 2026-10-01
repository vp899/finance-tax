"""数据模型"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from .database import Base


class Setting(Base):
    """键值设置（纳税人类型、会计准则、会计期间起止等）"""
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")


class Account(Base):
    """会计科目"""
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    parent_code = Column(String(20), nullable=True, index=True)
    # D=借方 C=贷方
    direction = Column(String(1), default="D")
    # asset / liability / equity / income / expense
    category = Column(String(20), default="asset")
    pinyin = Column(String(120), default="")  # 首字母 + 全拼，用于智能补全
    is_leaf = Column(Integer, default=1)
    currency = Column(String(10), default="CNY")
    unit = Column(String(20), default="")
    cashflow_code = Column(String(20), nullable=True)  # 默认现金流量项目
    level = Column(Integer, default=1)
    remark = Column(String(200), default="")


class OpeningBalance(Base):
    """科目期初余额（按会计年度存放）"""
    __tablename__ = "opening_balances"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    year = Column(String(4), nullable=False)
    debit = Column(Float, default=0.0)
    credit = Column(Float, default=0.0)
    quantity = Column(Float, default=0.0)
    __table_args__ = (UniqueConstraint("account_id", "year", name="uq_opening"),)


class VoucherType(Base):
    """凭证类型设置"""
    __tablename__ = "voucher_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), nullable=False)
    prefix = Column(String(4), nullable=False, unique=True)
    is_default = Column(Integer, default=0)


class Voucher(Base):
    """凭证"""
    __tablename__ = "vouchers"
    id = Column(Integer, primary_key=True)
    voucher_no = Column(String(30), unique=True, nullable=False)  # 记-202610-001
    vtype = Column(String(10), default="记")
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    period = Column(String(7), nullable=False, index=True)  # YYYY-MM
    status = Column(String(10), default="posted")  # draft / posted / voided
    attachment_count = Column(Integer, default=0)
    source = Column(String(20), default="manual")  # manual / carryover / import
    carryover_kind = Column(String(30), nullable=True)  # 结转类型
    created_at = Column(String(19), default="")
    posted_at = Column(String(19), default="")
    remark = Column(String(200), default="")
    entries = relationship(
        "VoucherEntry", back_populates="voucher",
        cascade="all, delete-orphan", order_by="VoucherEntry.line_no"
    )


class VoucherEntry(Base):
    """凭证分录"""
    __tablename__ = "voucher_entries"
    id = Column(Integer, primary_key=True)
    voucher_id = Column(Integer, ForeignKey("vouchers.id"), nullable=False, index=True)
    line_no = Column(Integer, default=1)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    summary = Column(String(200), default="")
    debit = Column(Float, default=0.0)
    credit = Column(Float, default=0.0)
    currency = Column(String(10), default="CNY")
    exchange_rate = Column(Float, default=1.0)
    quantity = Column(Float, default=0.0)
    unit = Column(String(20), default="")
    cashflow_code = Column(String(20), nullable=True)

    voucher = relationship("Voucher", back_populates="entries")
    account = relationship("Account")


class Period(Base):
    """会计期间（结账状态）"""
    __tablename__ = "periods"
    period = Column(String(7), primary_key=True)
    status = Column(String(10), default="open")  # open / closed
    closed_at = Column(String(19), default="")
    note = Column(String(200), default="")


class Unit(Base):
    """计量单位"""
    __tablename__ = "units"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    symbol = Column(String(10), default="")


class Currency(Base):
    """币种设置"""
    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(30), nullable=False)
    rate = Column(Float, default=1.0)
    is_default = Column(Integer, default=0)


class CashflowItem(Base):
    """现金流量项目"""
    __tablename__ = "cashflow_items"
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(20), default="operating")  # operating/investing/financing
    direction = Column(String(1), default="D")  # D=流入项 C=流出项


class AccountCashflowMap(Base):
    """科目现金流量对照表：对方科目 -> 现金流量项目"""
    __tablename__ = "account_cashflow_map"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    cashflow_code = Column(String(10), ForeignKey("cashflow_items.code"), nullable=False)
    __table_args__ = (UniqueConstraint("account_id", name="uq_acf"),)


class FixedAsset(Base):
    """固定资产（用于计提折旧）"""
    __tablename__ = "fixed_assets"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    original_value = Column(Float, default=0.0)
    residual_rate = Column(Float, default=0.05)  # 残值率
    life_months = Column(Integer, default=120)  # 使用寿命（月）
    expense_account_code = Column(String(20), default="5602")  # 费用科目
    dept = Column(String(50), default="")
    in_use = Column(Integer, default=1)


class IntangibleAsset(Base):
    """无形资产（用于摊销）"""
    __tablename__ = "intangible_assets"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    original_value = Column(Float, default=0.0)
    amort_months = Column(Integer, default=120)
    expense_account_code = Column(String(20), default="5602")
    in_use = Column(Integer, default=1)


class CarryoverRecord(Base):
    """结转记录（支持反结转）"""
    __tablename__ = "carryover_records"
    id = Column(Integer, primary_key=True)
    kind = Column(String(30), nullable=False)  # sales_cost / salary / depreciation / amortization / profit / tax / income_tax / vat_free
    period = Column(String(7), nullable=False, index=True)
    voucher_id = Column(Integer, ForeignKey("vouchers.id"), nullable=False)
    amount = Column(Float, default=0.0)
    status = Column(String(10), default="active")  # active / reversed
    created_at = Column(String(19), default="")
    note = Column(String(200), default="")
    voucher = relationship("Voucher")


Index("ix_entry_account_voucher", VoucherEntry.account_id, VoucherEntry.voucher_id)
