/**
 * 其余页面冒烟测试：账簿 / 报表 / 凭证 / 设置（mock 后端接口）
 * 目标：保证页面组件可编译可渲染，年度/区间控件可用。
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import BooksPage from "@/app/books/page";
import ReportsPage from "@/app/reports/page";
import VouchersPage from "@/app/vouchers/page";
import SettingsPage from "@/app/settings/page";

const okJson = (data) => ({ ok: true, status: 200, json: async () => data });

function mockRoutes(routes) {
  global.fetch = jest.fn((url) => {
    const u = String(url);
    for (const [key, data] of Object.entries(routes)) {
      if (u.includes(key)) return Promise.resolve(okJson(data));
    }
    return Promise.resolve(okJson(Array.isArray(routes.__default) ? routes.__default : {}));
  });
}

afterEach(() => jest.restoreAllMocks());

const EMPTY_BOOKS = {
  rows: [
    {
      code: "1002", name: "银行存款", level: 1, direction: "D",
      opening_debit: 100, opening_credit: 0, period_debit: 10, period_credit: 5,
      closing_debit: 105, closing_credit: 0,
    },
  ],
  from_period: "2026-01", to_period: "2026-01",
};

describe("账簿查询页面", () => {
  test("总账渲染 + 年度/区间切换", async () => {
    mockRoutes({ "/api/books/general-ledger": EMPTY_BOOKS });
    render(<BooksPage />);
    await waitFor(() => expect(screen.getByText(/银行存款/)).toBeInTheDocument());
    // 切换到按年度
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "year" } });
    expect(screen.getByDisplayValue("2026")).toBeInTheDocument();
  });

  test("试算平衡表标签页", async () => {
    mockRoutes({
      "/api/books/general-ledger": EMPTY_BOOKS,
      "/api/books/trial-balance": {
        rows: [{ code: "1002", name: "银行存款", debit: 105, credit: 0, is_leaf: true,
                 opening_debit: 100, opening_credit: 0, period_debit: 10, period_credit: 5 }],
        total_debit: 105, total_credit: 105, balanced: true, difference: 0,
      },
    });
    render(<BooksPage />);
    fireEvent.click(await screen.findByText("试算平衡表"));
    await waitFor(() => expect(screen.getByText("试算平衡")).toBeInTheDocument());
    expect(screen.getByText("期初借方")).toBeInTheDocument();
  });
});

describe("财务报表页面", () => {
  test("资产负债表渲染", async () => {
    mockRoutes({
      "/api/reports/balance-sheet": {
        balanced: true, asset_total: 100, liability_equity_total: 100,
        rows: [{ name: "货币资金", ending: 100, beginning: 50, type: "line", group: "asset_cur" }],
      },
    });
    render(<ReportsPage />);
    await waitFor(() => expect(screen.getByText("货币资金")).toBeInTheDocument());
    expect(screen.getByText("✓ 表内平衡")).toBeInTheDocument();
  });

  test("利润表切换", async () => {
    mockRoutes({
      "/api/reports/balance-sheet": { balanced: true, rows: [] },
      "/api/reports/income": {
        rows: [{ name: "一、营业收入", current: 100, ytd: 200, type: "line" }],
      },
    });
    render(<ReportsPage />);
    fireEvent.click(await screen.findByText("利润表"));
    await waitFor(() => expect(screen.getByText("一、营业收入")).toBeInTheDocument());
  });
});

describe("凭证管理页面", () => {
  test("凭证列表与删除按钮", async () => {
    mockRoutes({
      "/api/vouchers?": {
        total: 1, page: 1, size: 20,
        rows: [{
          id: 7, voucher_no: "记-202601-001", date: "2026-01-05", period: "2026-01",
          status: "posted", source: "manual", first_summary: "测试摘要",
          total_debit: 10, total_credit: 10, entry_count: 2,
        }],
      },
    });
    render(<VouchersPage />);
    await waitFor(() => expect(screen.getByText("记-202601-001")).toBeInTheDocument());
    expect(screen.getByText("删除")).toBeInTheDocument();
    expect(screen.getByText("作废")).toBeInTheDocument();
    expect(screen.getByText(/新增凭证/)).toBeInTheDocument();
  });

  test("凭证汇总表", async () => {
    mockRoutes({
      "/api/vouchers/summary": {
        rows: [{ vtype: "记", count: 2, debit: 20, credit: 20 }],
        count: 2, total_debit: 20, total_credit: 20, balanced: true,
      },
    });
    render(<VouchersPage />);
    fireEvent.click(await screen.findByText("凭证汇总表"));
    await waitFor(() => expect(screen.getByText("凭证张数")).toBeInTheDocument());
    expect(screen.getByText("合计")).toBeInTheDocument();
  });
});

describe("财税设置页面", () => {
  test("期初余额编辑页", async () => {
    mockRoutes({
      "/api/accounts/openings/list": {
        year: "2026",
        rows: [
          { account_id: 1, code: "1002", name: "银行存款", direction: "D",
            debit: 100, credit: 0, quantity: 0, is_leaf: true },
          { account_id: 2, code: "3001", name: "实收资本", direction: "C",
            debit: 0, credit: 100, quantity: 0, is_leaf: true },
        ],
        total_debit: 100, total_credit: 100, balanced: true,
      },
    });
    render(<SettingsPage />);
    fireEvent.click(await screen.findByText("科目期初"));
    await waitFor(() => expect(screen.getByText("保存期初")).toBeInTheDocument());
    expect(screen.getByText("试算平衡")).toBeInTheDocument();
    // 年度/区间说明可见
    expect(screen.getByText(/可直接修改已有期初/)).toBeInTheDocument();
  });
});
