/**
 * 余额表：全零科目默认隐藏、可切换显示
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import BooksPage from "@/app/books/page";

const okJson = (data) => ({ ok: true, status: 200, json: async () => data });

const ROWS = [
  {
    code: "1002", name: "银行存款", level: 1, direction: "D",
    opening_debit: 1000, opening_credit: 0, period_debit: 100, period_credit: 0,
    closing_debit: 1100, closing_credit: 0,
  },
  {
    code: "1001", name: "库存现金", level: 1, direction: "D",
    opening_debit: 0, opening_credit: 0, period_debit: 0, period_credit: 0,
    closing_debit: 0, closing_credit: 0,
  },
];

function mockRoutes(routes) {
  global.fetch = jest.fn((url) => {
    const u = String(url);
    for (const [key, data] of Object.entries(routes)) {
      if (u.includes(key)) return Promise.resolve(okJson(data));
    }
    return Promise.resolve(okJson([]));
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

test("余额表默认隐藏全零科目，可勾选显示", async () => {
  mockRoutes({ "/api/books/balance-table": { rows: ROWS } });
  render(<BooksPage />);
  fireEvent.click(screen.getByText("余额表"));

  const checkbox = await screen.findByLabelText(/隐藏全零科目/);
  await waitFor(() => expect(checkbox).toBeChecked());

  // 默认隐藏：全零科目不出现，有余额的科目正常显示
  expect(screen.queryByText("库存现金")).toBeNull();
  expect(screen.getByText("银行存款")).toBeInTheDocument();

  // 取消勾选后显示全零科目
  fireEvent.click(checkbox);
  await waitFor(() => expect(screen.getByText("库存现金")).toBeInTheDocument());
});

test("隐藏状态记忆在 localStorage", async () => {
  window.localStorage.setItem("ft.hideZeroBalance", "0");
  mockRoutes({ "/api/books/balance-table": { rows: ROWS } });
  render(<BooksPage />);
  fireEvent.click(screen.getByText("余额表"));
  const checkbox = await screen.findByLabelText(/隐藏全零科目/);
  await waitFor(() => expect(checkbox).not.toBeChecked());
  expect(screen.getByText("库存现金")).toBeInTheDocument();
});
