/**
 * 月份结账状态 / 批量结账 / 同步月份数据 / 选中月份同步（mock 后端接口）
 */
import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import CarryoverPage from "@/app/carryover/page";
import { PeriodRange } from "@/components/ui";
import { curPeriod, defaultRange, realPeriod, setSelMonth } from "@/lib/api";

const okJson = (data) => ({ ok: true, status: 200, json: async () => data });

const PERIODS = [
  {
    period: "2021-06", status: "closed", closed_at: "2021-07-01 10:00:00",
    note: "历史数据已在其它系统结账",
    voucher_count: 40, import_count: 40, manual_count: 0,
    draft_count: 0, void_count: 0, total_debit: 1000, total_credit: 1000,
  },
  {
    period: "2021-05", status: "open", closed_at: "", note: "",
    voucher_count: 12, import_count: 12, manual_count: 0,
    draft_count: 1, void_count: 0, total_debit: 500, total_credit: 500,
  },
];

function mockRoutes(routes, calls) {
  global.fetch = jest.fn((url, opts) => {
    const u = String(url);
    if (calls) calls.push({ url: u, method: opts?.method || "GET", body: opts?.body });
    for (const [key, data] of Object.entries(routes)) {
      if (u.includes(key)) return Promise.resolve(okJson(data));
    }
    return Promise.resolve(okJson({}));
  });
}

// 页面含多张月份表格（月份结账状态 + 每月结转状态矩阵），查询时限定到目标表格
const monthPanel = () => screen.getByText("月份结账状态").closest(".card");
const monthCell = (period) => within(monthPanel()).findByText(period);

beforeEach(() => {
  window.localStorage.clear();
  window.confirm = jest.fn(() => true);
});

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("月份结账状态列表", () => {
  test("展示每月结账状态与月份数据", async () => {
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS,
      "/api/carryover/kinds": [],
    });
    render(<CarryoverPage />);
    await waitFor(() => expect(screen.getByText("月份结账状态")).toBeInTheDocument());
    expect(await monthCell("2021-06")).toBeInTheDocument();
    expect(screen.getByText("已结账")).toBeInTheDocument();
    expect(screen.getByText("未结账")).toBeInTheDocument();
    expect(within(monthPanel()).getByText("会计期间")).toBeInTheDocument();
    expect(within(monthPanel()).getByText("其中导入")).toBeInTheDocument();
  });

  test("点击月份行选中月份并同步该月数据", async () => {
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS,
      "/api/carryover/kinds": [],
    });
    render(<CarryoverPage />);
    fireEvent.click(await monthCell("2021-05"));
    await waitFor(() => expect(curPeriod()).toBe("2021-05"));
    // 页面月份输入与结转记录的区间选择器都同步到选中月份
    expect(screen.getAllByDisplayValue("2021-05").length).toBeGreaterThan(0);
    expect(window.localStorage.getItem("finance.selMonth")).toBe("2021-05");
  });

  test("批量结账按勾选月份调用批量接口", async () => {
    const calls = [];
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS,
      "/api/carryover/kinds": [],
      "/api/carryover/close-batch": { results: [{ period: "2021-05", ok: true, status: "closed" }], closed: 1, failed: 0 },
    }, calls);
    render(<CarryoverPage />);
    const row = (await monthCell("2021-05")).closest("tr");
    fireEvent.click(row.querySelector('input[type="checkbox"]'));
    fireEvent.click(screen.getByText("批量结账"));
    await waitFor(() => {
      const hit = calls.find((c) => c.url.includes("/api/carryover/close-batch"));
      expect(hit).toBeTruthy();
      const body = JSON.parse(hit.body);
      expect(body.periods).toEqual(["2021-05"]);
      expect(body.skip_checks).toBe(true); // 默认跳过检查（历史数据已在其它系统结账）
    });
    await waitFor(() =>
      expect(screen.getByText(/批量结账完成：成功 1 个期间/)).toBeInTheDocument()
    );
  });

  test("批量反结账调用批量接口", async () => {
    const calls = [];
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS,
      "/api/carryover/kinds": [],
      "/api/carryover/open-batch": { results: [], opened: 1, failed: 0 },
    }, calls);
    render(<CarryoverPage />);
    const row = (await monthCell("2021-06")).closest("tr");
    fireEvent.click(row.querySelector('input[type="checkbox"]'));
    fireEvent.click(screen.getByText("批量反结账"));
    await waitFor(() => {
      const hit = calls.find((c) => c.url.includes("/api/carryover/open-batch"));
      expect(hit).toBeTruthy();
      expect(JSON.parse(hit.body).periods).toEqual(["2021-06"]);
    });
    await waitFor(() =>
      expect(screen.getByText(/批量反结账完成：成功 1 个期间/)).toBeInTheDocument()
    );
  });

  test("同步月份数据调用同步接口", async () => {
    const calls = [];
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS,
      "/api/carryover/kinds": [],
      "/api/carryover/periods/sync": { synced: ["2021-05", "2021-06"], created: [], periods: PERIODS },
    }, calls);
    render(<CarryoverPage />);
    const row = (await monthCell("2021-05")).closest("tr");
    fireEvent.click(row.querySelector('input[type="checkbox"]'));
    fireEvent.click(screen.getByText("同步月份数据"));
    await waitFor(() => {
      const hit = calls.find((c) => c.url.includes("/api/carryover/periods/sync"));
      expect(hit).toBeTruthy();
      expect(JSON.parse(hit.body).periods).toEqual(["2021-05"]);
    });
    await waitFor(() =>
      expect(screen.getByText(/月份数据已同步/)).toBeInTheDocument()
    );
  });

  test("未勾选月份时给出提示", async () => {
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS,
      "/api/carryover/kinds": [],
    });
    render(<CarryoverPage />);
    fireEvent.click(await screen.findByText("批量结账"));
    await waitFor(() =>
      expect(screen.getByText(/请先勾选需要操作的会计期间/)).toBeInTheDocument()
    );
  });
});

describe("选中月份同步", () => {
  test("设置选中月份后全局月份查询口径同步", () => {
    setSelMonth("2021-06");
    expect(curPeriod()).toBe("2021-06");
    const r = defaultRange();
    expect(r.month).toBe("2021-06");
    expect(r.year).toBe("2021");
    expect(r.from).toBe("2021-01");
    expect(r.to).toBe("2021-06");
  });

  test("选中月份变化时 PeriodRange 同步月份数据", async () => {
    const value = defaultRange();
    const onChange = jest.fn();
    render(<PeriodRange value={value} onChange={onChange} />);
    setSelMonth("2021-06");
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(onChange.mock.calls[0][0].month).toBe("2021-06");
    expect(onChange.mock.calls[0][0].mode).toBe("month");
  });

  test("清除选中月份回退到当前月份", () => {
    setSelMonth("2021-06");
    setSelMonth("");
    expect(curPeriod()).toBe(realPeriod());
  });
});

describe("每月结转状态", () => {
  const KINDS = [
    { kind: "sales_cost", name: "结转销售成本", order: 10, enabled: true },
    { kind: "profit", name: "结转本期损益", order: 170, enabled: true },
    { kind: "retain_profit", name: "结转未分配利润", order: 180, enabled: true },
  ];
  const PERIODS_WITH_CARRY = [
    {
      period: "2021-06", status: "closed", closed_at: "2021-07-01 10:00:00", note: "",
      voucher_count: 5, import_count: 5, manual_count: 0,
      draft_count: 0, void_count: 0, total_debit: 100, total_credit: 100,
      carryover: {
        count: 2, amount: 700, kinds: ["sales_cost", "profit"],
        kind_names: ["结转销售成本", "结转本期损益"], profit_closed: true,
        records: [
          { id: 1, kind: "sales_cost", kind_name: "结转销售成本", amount: 200,
            status: "active", voucher_no: "记-202106-003", source_no: "转-1", source: "import" },
          { id: 2, kind: "profit", kind_name: "结转本期损益", amount: 500,
            status: "active", voucher_no: "记-202106-004", source_no: "转-2", source: "import" },
        ],
      },
    },
    {
      period: "2021-05", status: "open", closed_at: "", note: "",
      voucher_count: 3, import_count: 3, manual_count: 0,
      draft_count: 0, void_count: 0, total_debit: 90, total_credit: 90,
      carryover: {
        count: 0, amount: 0, kinds: [], kind_names: [], profit_closed: false, records: [],
      },
    },
  ];

  test("月份列表显示结转状态与损益结平", async () => {
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS_WITH_CARRY,
      "/api/carryover/kinds": KINDS,
    });
    render(<CarryoverPage />);
    expect(await screen.findByText("已结转 2 项")).toBeInTheDocument();
    expect(screen.getByText("未结转")).toBeInTheDocument();
    expect(screen.getAllByText("已结平").length).toBeGreaterThan(0);
    expect(screen.getAllByText("未结平").length).toBeGreaterThan(0);
  });

  test("矩阵按月展示已执行的结转步骤", async () => {
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS_WITH_CARRY,
      "/api/carryover/kinds": KINDS,
    });
    render(<CarryoverPage />);
    await screen.findByText("已结转 2 项"); // 等待月份数据渲染
    const matrix = () => within(screen.getByText("每月结转状态").closest(".card"));
    // 表头为结转步骤简称
    expect(matrix().getAllByText("销售成本").length).toBeGreaterThan(0);
    expect(matrix().getAllByText("结转损益").length).toBeGreaterThan(0);
    // 2021-06 两步已结转，其余格为未执行标记
    expect(matrix().getAllByText("✓").length).toBe(2);
    expect(matrix().getAllByText("·").length).toBe(4);
    // 单元格提示含凭证号与导入来源
    expect(matrix().getAllByTitle(/导入识别/).length).toBe(2);
  });

  test("矩阵支持停用步骤的展示", async () => {
    mockRoutes({
      "/api/carryover/records": [],
      "/api/carryover/periods": PERIODS_WITH_CARRY,
      "/api/carryover/kinds": KINDS.map((k) =>
        k.kind === "retain_profit" ? { ...k, enabled: false } : k),
    });
    render(<CarryoverPage />);
    await screen.findByText("已结转 2 项"); // 等待月份数据渲染
    expect(screen.getByText("每月结转状态")).toBeInTheDocument();
    expect(screen.getAllByText("未分配利润").length).toBeGreaterThan(0);
  });
});
