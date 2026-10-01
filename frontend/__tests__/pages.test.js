/**
 * 页面级测试：仪表盘 / 结转页（mock 后端接口）
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Dashboard from "@/app/page";
import CarryoverPage from "@/app/carryover/page";

const okJson = (data) => ({ ok: true, status: 200, json: async () => data });

const INCOME = {
  rows: [
    { name: "一、营业收入", current: 100000, ytd: 300000, type: "line" },
    { name: "　减：营业成本", current: 50000, ytd: 150000, type: "line" },
    { name: "　　　营业税金及附加", current: 300, ytd: 900, type: "line" },
    { name: "　　　销售费用", current: 0, ytd: 0, type: "line" },
    { name: "　　　管理费用", current: 20000, ytd: 60000, type: "line" },
    { name: "　　　财务费用", current: 0, ytd: 0, type: "line" },
    { name: "　加：投资收益（损失以“-”号填列）", current: 0, ytd: 0, type: "line" },
    { name: "二、营业利润（亏损以“-”号填列）", current: 29700, ytd: 89100, type: "calc" },
    { name: "　加：营业外收入", current: 0, ytd: 0, type: "line" },
    { name: "　减：营业外支出", current: 0, ytd: 0, type: "line" },
    { name: "三、利润总额（亏损以“-”号填列）", current: 29700, ytd: 89100, type: "calc" },
    { name: "　减：所得税费用", current: 0, ytd: 0, type: "line" },
    { name: "四、净利润（净亏损以“-”号填列）", current: 29700, ytd: 89100, type: "calc" },
  ],
  period: "2026-10",
};

const BS = {
  balanced: true,
  asset_total: 601550,
  liability_equity_total: 601550,
  rows: [
    { name: "货币资金", ending: 421000, beginning: 400000, type: "line", group: "asset_cur" },
    { name: "资产总计", ending: 601550, beginning: 580000, type: "total", group: "asset_total" },
    { name: "负债合计", ending: 80407.5, beginning: 50000, type: "sub", group: "liab_total" },
    { name: "所有者权益合计", ending: 521142.5, beginning: 530000, type: "sub", group: "equity_total" },
    { name: "未分配利润", ending: 21142.5, beginning: 30000, type: "line", group: "equity" },
    { name: "负债和所有者权益总计", ending: 601550, beginning: 580000, type: "total", group: "le_total" },
  ],
};

const VSUM = {
  rows: [{ vtype: "记", count: 12, debit: 500000, credit: 500000 }],
  count: 12,
  total_debit: 500000,
  total_credit: 500000,
  balanced: true,
};

const TRIAL = { rows: [], total_debit: 600000, total_credit: 600000, balanced: true };

function mockRoutes(routes) {
  global.fetch = jest.fn((url) => {
    const u = String(url);
    for (const [key, data] of Object.entries(routes)) {
      if (u.includes(key)) return Promise.resolve(okJson(data));
    }
    return Promise.resolve(okJson({}));
  });
}

afterEach(() => jest.restoreAllMocks());

describe("仪表盘页面", () => {
  test("加载后展示经营指标卡片", async () => {
    mockRoutes({
      "/api/reports/income": INCOME,
      "/api/reports/balance-sheet": BS,
      "/api/vouchers/summary": VSUM,
      "/api/books/trial-balance": TRIAL,
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getAllByText("100,000.00").length).toBeGreaterThan(0));
    expect(screen.getByText("本期营业收入")).toBeInTheDocument();
    expect(screen.getByText("资产总计")).toBeInTheDocument();
    expect(screen.getByText("未分配利润")).toBeInTheDocument();
    expect(screen.getByText("本期凭证数")).toBeInTheDocument();
  });

  test("展示平衡状态徽章", async () => {
    mockRoutes({
      "/api/reports/income": INCOME,
      "/api/reports/balance-sheet": BS,
      "/api/vouchers/summary": VSUM,
      "/api/books/trial-balance": TRIAL,
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("试算平衡")).toBeInTheDocument());
    expect(screen.getByText("资产负债表平衡")).toBeInTheDocument();
  });

  test("后端不可用时给出错误提示", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("Failed to fetch"));
    render(<Dashboard />);
    await waitFor(() =>
      expect(screen.getByText(/无法连接后端服务/)).toBeInTheDocument()
    );
  });

  test("快捷入口渲染", async () => {
    mockRoutes({
      "/api/reports/income": INCOME,
      "/api/reports/balance-sheet": BS,
      "/api/vouchers/summary": VSUM,
      "/api/books/trial-balance": TRIAL,
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("录入凭证")).toBeInTheDocument());
    expect(screen.getByText("月末结转")).toBeInTheDocument();
    expect(screen.getByText("生成报表")).toBeInTheDocument();
    expect(screen.getByText("财税设置")).toBeInTheDocument();
  });

  test("不平衡时徽章变红", async () => {
    mockRoutes({
      "/api/reports/income": INCOME,
      "/api/reports/balance-sheet": { ...BS, balanced: false },
      "/api/vouchers/summary": VSUM,
      "/api/books/trial-balance": { ...TRIAL, balanced: false },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("试算不平衡")).toBeInTheDocument());
    expect(screen.getByText("资产负债表不平衡")).toBeInTheDocument();
  });
});

const RECORDS = [
  {
    id: 1, kind: "depreciation", period: "2026-10", amount: 950,
    status: "active", created_at: "2026-10-01 10:00:00", note: "计提折旧",
    voucher_id: 11, voucher_no: "转-202610-001",
  },
  {
    id: 2, kind: "sales_cost", period: "2026-10", amount: 50000,
    status: "reversed", created_at: "2026-10-01 10:01:00", note: "",
    voucher_id: 12, voucher_no: "转-202610-002",
  },
];

describe("结转与结账页面", () => {
  test("展示 8 项结转操作", async () => {
    mockRoutes({ "/api/carryover/records": RECORDS, "/api/carryover/periods": [] });
    render(<CarryoverPage />);
    await waitFor(() => expect(screen.getAllByText("结转销售成本").length).toBeGreaterThan(0));
    expect(screen.getAllByText("计提工资").length).toBeGreaterThan(0);
    expect(screen.getAllByText("计提折旧").length).toBeGreaterThan(0);
    expect(screen.getAllByText("摊销无形资产").length).toBeGreaterThan(0);
    expect(screen.getAllByText("结转本期损益").length).toBeGreaterThan(0);
    expect(screen.getAllByText("计提税金").length).toBeGreaterThan(0);
    expect(screen.getAllByText("计提所得税").length).toBeGreaterThan(0);
    expect(screen.getAllByText("免交增值税").length).toBeGreaterThan(0);
  });

  test("结转记录列表与状态", async () => {
    mockRoutes({ "/api/carryover/records": RECORDS, "/api/carryover/periods": [] });
    render(<CarryoverPage />);
    await waitFor(() => expect(screen.getByText("转-202610-001")).toBeInTheDocument());
    expect(screen.getByText("有效")).toBeInTheDocument();
    expect(screen.getByText("已反结转")).toBeInTheDocument();
  });

  test("点击操作卡片打开预览弹窗", async () => {
    mockRoutes({
      "/api/carryover/records": RECORDS,
      "/api/carryover/periods": [],
      "/api/carryover/preview/depreciation": {
        items: [{ id: 1, name: "设备A", amount: 950 }], total: 950,
      },
    });
    render(<CarryoverPage />);
    fireEvent.click(await screen.findByText("计提折旧"));
    await waitFor(() =>
      expect(screen.getByText("本月折旧合计")).toBeInTheDocument()
    );
    expect(screen.getAllByText("950.00").length).toBeGreaterThan(0);
  });

  test("结转执行提交并提示成功", async () => {
    mockRoutes({
      "/api/carryover/records": RECORDS,
      "/api/carryover/periods": [],
      "/api/carryover/preview/depreciation": {
        items: [{ id: 1, name: "设备A", amount: 950 }], total: 950,
      },
      "/api/carryover/depreciation": {
        record_id: 9, voucher_id: 99, voucher_no: "转-202610-009", amount: 950,
      },
    });
    render(<CarryoverPage />);
    fireEvent.click(await screen.findByText("计提折旧"));
    fireEvent.click(await screen.findByText("确认计提折旧"));
    await waitFor(() =>
      expect(screen.getByText(/计提折旧完成/)).toBeInTheDocument()
    );
  });

  test("后端报错展示错误信息", async () => {
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes("/preview/depreciation"))
        return Promise.resolve(okJson({ items: [], total: 0 }));
      if (u.includes("/api/carryover/depreciation"))
        return Promise.resolve({
          ok: false, status: 400,
          json: async () => ({ detail: "尚未录入固定资产" }),
        });
      return Promise.resolve(okJson(u.includes("periods") ? [] : RECORDS));
    });
    render(<CarryoverPage />);
    fireEvent.click(await screen.findByText("计提折旧"));
    fireEvent.click(await screen.findByText("确认计提折旧"));
    await waitFor(() =>
      expect(screen.getByText("尚未录入固定资产")).toBeInTheDocument()
    );
  });
});
