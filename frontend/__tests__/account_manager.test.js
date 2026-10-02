/**
 * 科目表管理组件测试：增删改/上下级/禁用/批量/导入导出/数据清零/辅助核算
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AccountManager from "@/components/AccountManager";

const okJson = (data) => ({ ok: true, status: 200, json: async () => data });

const ACCOUNTS = [
  {
    id: 1, code: "1002", name: "银行存款", parent_code: null, direction: "D",
    category: "asset", category_name: "资产", pinyin: "yhck", is_leaf: false,
    is_disabled: false, quantity_accounting: false, level: 1, currency: "CNY",
    unit: "", remark: "", aux_project: false, aux_customer: false,
    aux_supplier: false, aux_dept: false, aux_employee: false, aux_inventory: false,
    opening: { debit: 1000, credit: 0, year_debit: 1000, year_credit: 0, quantity: 0 },
  },
  {
    id: 2, code: "100201", name: "工行存款", parent_code: "1002", direction: "D",
    category: "asset", category_name: "资产", pinyin: "", is_leaf: true,
    is_disabled: true, quantity_accounting: true, level: 2, currency: "CNY",
    unit: "个", remark: "", aux_project: true, aux_customer: false,
    aux_supplier: false, aux_dept: false, aux_employee: false, aux_inventory: false,
    opening: { debit: 500, credit: 0, year_debit: 500, year_credit: 0, quantity: 3 },
  },
  {
    id: 3, code: "4001", name: "生产成本", parent_code: null, direction: "D",
    category: "cost", category_name: "成本", pinyin: "", is_leaf: true,
    is_disabled: false, quantity_accounting: false, level: 1, currency: "CNY",
    unit: "", remark: "", aux_project: false, aux_customer: false,
    aux_supplier: false, aux_dept: false, aux_employee: false, aux_inventory: false,
    opening: { debit: 0, credit: 0, year_debit: 0, year_credit: 0, quantity: 0 },
  },
];

const SETTINGS = {
  aux_switch_project: "1", aux_switch_customer: "1", aux_switch_supplier: "1",
  aux_switch_dept: "1", aux_switch_employee: "1", aux_switch_inventory: "0",
  decimal_qty: "2", decimal_price: "2", decimal_rate: "6",
};

function mockRoutes(routes) {
  global.fetch = jest.fn((url, opts) => {
    const u = String(url);
    for (const [key, data] of Object.entries(routes)) {
      if (u.includes(key)) return Promise.resolve(okJson(data));
    }
    return Promise.resolve(okJson({}));
  });
}

afterEach(() => jest.restoreAllMocks());

describe("科目表管理", () => {
  test("表格展示科目字段与期初余额", async () => {
    mockRoutes({ "/api/accounts?": ACCOUNTS, "/api/settings": SETTINGS });
    render(<AccountManager />);
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    expect(screen.getByText("科目编码")).toBeInTheDocument();
    expect(screen.getByText("核算类型")).toBeInTheDocument();
    expect(screen.getByText("借贷方向")).toBeInTheDocument();
    expect(screen.getAllByText("资产").length).toBeGreaterThan(0);
    expect(screen.getAllByText("成本").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1,000.00 借/).length).toBeGreaterThan(0);
    expect(screen.getByText("停用")).toBeInTheDocument();
  });

  test("新增科目提交完整载荷", async () => {
    const posts = [];
    global.fetch = jest.fn((url, opts) => {
      const u = String(url);
      if (u.includes("/api/accounts?")) return Promise.resolve(okJson(ACCOUNTS));
      if (u.includes("/api/settings")) return Promise.resolve(okJson(SETTINGS));
      if (u.endsWith("/api/accounts") && opts && opts.method === "POST") {
        posts.push(JSON.parse(opts.body));
        return Promise.resolve(okJson({ id: 9, code: "1003", name: "其他货币资金" }));
      }
      return Promise.resolve(okJson({}));
    });
    render(<AccountManager />);
    fireEvent.click(await screen.findByText("＋ 新增科目"));
    const modal = screen.getByText("科目编码 *").closest(".max-w-5xl");
    const inputs = modal.querySelectorAll("input");
    fireEvent.change(inputs[0], { target: { value: "1003" } });
    fireEvent.change(inputs[1], { target: { value: "其他货币资金" } });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0].code).toBe("1003");
    expect(posts[0].name).toBe("其他货币资金");
    expect(posts[0].category).toBe("asset");
    expect(posts[0].quantity_accounting).toBe(false);
  });

  test("编辑科目与添加下级", async () => {
    mockRoutes({ "/api/accounts?": ACCOUNTS, "/api/settings": SETTINGS });
    render(<AccountManager />);
    fireEvent.click((await screen.findAllByText("添加下级"))[0]);
    await waitFor(() => expect(screen.getByText("新增科目")).toBeInTheDocument());
    // 上级科目预填 1002
    expect(screen.getByDisplayValue("1002 银行存款")).toBeInTheDocument();
  });

  test("停用的辅助核算开关不可勾选", async () => {
    mockRoutes({ "/api/accounts?": ACCOUNTS, "/api/settings": SETTINGS });
    render(<AccountManager />);
    fireEvent.click((await screen.findAllByText("编辑"))[1]);
    await waitFor(() => expect(screen.getByText("辅助核算：")).toBeInTheDocument());
    const inventory = screen.getByText("存货").closest("label").querySelector("input");
    expect(inventory).toBeDisabled();
    const project = screen.getByText("项目").closest("label").querySelector("input");
    expect(project).not.toBeDisabled();
    expect(project.checked).toBe(true);
  });

  test("批量禁用提交勾选科目", async () => {
    const posts = [];
    global.fetch = jest.fn((url, opts) => {
      const u = String(url);
      if (u.includes("/api/accounts?")) return Promise.resolve(okJson(ACCOUNTS));
      if (u.includes("/api/settings")) return Promise.resolve(okJson(SETTINGS));
      if (u.includes("/api/accounts/batch")) {
        posts.push(JSON.parse(opts.body));
        return Promise.resolve(okJson({ ok_count: 1, results: [] }));
      }
      return Promise.resolve(okJson({}));
    });
    render(<AccountManager />);
    await waitFor(() => expect(screen.getByText("银行存款")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("checkbox")[1]); // 勾选第一行
    fireEvent.click(screen.getByText("批量禁用"));
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0].action).toBe("disable");
    expect(posts[0].ids).toEqual([1]);
  });

  test("导出科目表/期初链接带年份", async () => {
    mockRoutes({ "/api/accounts?": ACCOUNTS, "/api/settings": SETTINGS });
    render(<AccountManager />);
    await waitFor(() => expect(screen.getByText("导出科目表")).toBeInTheDocument());
    expect(screen.getByText("导出科目表").getAttribute("href")).toContain("/api/accounts/export.xlsx");
    expect(screen.getByText("导出科目期初").getAttribute("href")).toContain("year=");
  });

  test("数据清零需勾选确认", async () => {
    mockRoutes({ "/api/accounts?": ACCOUNTS, "/api/settings": SETTINGS });
    render(<AccountManager />);
    fireEvent.click(await screen.findByText("数据清零"));
    await waitFor(() => expect(screen.getByText("我已了解数据清零不可恢复，确认执行")).toBeInTheDocument());
    const run = screen.getByText("执行数据清零");
    expect(run).toBeDisabled();
    fireEvent.click(screen.getByText(/我已了解数据清零不可恢复/));
    expect(run).not.toBeDisabled();
  });

  test("数据清零执行并提示", async () => {
    global.fetch = jest.fn((url, opts) => {
      const u = String(url);
      if (u.includes("/api/accounts?")) return Promise.resolve(okJson(ACCOUNTS));
      if (u.includes("/api/settings")) return Promise.resolve(okJson(SETTINGS));
      if (u.includes("/api/accounts/data/clear"))
        return Promise.resolve(okJson({ ok: true, cleared: { vouchers: 3, carryover_records: 1 } }));
      return Promise.resolve(okJson({}));
    });
    render(<AccountManager />);
    fireEvent.click(await screen.findByText("数据清零"));
    await waitFor(() => expect(screen.getByText(/我已了解数据清零不可恢复/)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/我已了解数据清零不可恢复/));
    fireEvent.click(screen.getByText("执行数据清零"));
    await waitFor(() => expect(screen.getByText(/数据清零完成/)).toBeInTheDocument());
  });
});
