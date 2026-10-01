/**
 * lib/api.js 单元测试
 */
import {
  apiGet,
  apiPost,
  apiPut,
  apiUpload,
  apiUrl,
  curPeriod,
  defaultRange,
  downloadUrl,
  fmtMoney,
  rangeFromTo,
  rangeLabel,
  rangeQuery,
  shiftPeriod,
} from "@/lib/api";

const okJson = (data) => ({
  ok: true,
  status: 200,
  json: async () => data,
});

describe("fmtMoney 金额格式化", () => {
  test("千分位 + 两位小数", () => {
    expect(fmtMoney(1234567.891)).toBe("1,234,567.89");
  });
  test("整数补两位小数", () => {
    expect(fmtMoney(100)).toBe("100.00");
  });
  test("负数保留符号", () => {
    expect(fmtMoney(-50.5)).toBe("-50.50");
  });
  test("null/undefined/空串 返回空", () => {
    expect(fmtMoney(null)).toBe("");
    expect(fmtMoney(undefined)).toBe("");
    expect(fmtMoney("")).toBe("");
  });
  test("0 正常显示", () => {
    expect(fmtMoney(0)).toBe("0.00");
  });
});

describe("期间工具", () => {
  test("curPeriod 返回 YYYY-MM", () => {
    expect(curPeriod()).toMatch(/^\d{4}-\d{2}$/);
  });
  test("shiftPeriod 跨年进位", () => {
    expect(shiftPeriod("2026-12", 1)).toBe("2027-01");
  });
  test("shiftPeriod 跨年退位", () => {
    expect(shiftPeriod("2026-01", -1)).toBe("2025-12");
  });
  test("shiftPeriod 同年平移", () => {
    expect(shiftPeriod("2026-06", 2)).toBe("2026-08");
    expect(shiftPeriod("2026-06", -2)).toBe("2026-04");
  });
  test("shiftPeriod 多月进位", () => {
    expect(shiftPeriod("2026-11", 5)).toBe("2027-04");
  });
});

describe("URL 构造", () => {
  test("apiUrl 拼接", () => {
    expect(apiUrl("/api/health")).toContain("/api/health");
  });
  test("downloadUrl 拼接", () => {
    expect(downloadUrl("/api/data/backup/download")).toContain("/api/data/backup/download");
  });
});

describe("apiGet / apiPost / apiPut", () => {
  afterEach(() => jest.restoreAllMocks());

  test("apiGet 成功解析 JSON", async () => {
    global.fetch = jest.fn().mockResolvedValue(okJson({ a: 1 }));
    await expect(apiGet("/x")).resolves.toEqual({ a: 1 });
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test("apiGet 非 2xx 抛出后端错误信息", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "借贷不平衡" }),
    });
    await expect(apiGet("/x")).rejects.toThrow("借贷不平衡");
  });

  test("apiGet 非 2xx 且无 detail 时用默认文案", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    });
    await expect(apiGet("/x")).rejects.toThrow("请求失败 (500)");
  });

  test("apiPost 发送 JSON 与请求头", async () => {
    global.fetch = jest.fn().mockResolvedValue(okJson({ ok: true }));
    await apiPost("/x", { b: 2 });
    const [, init] = global.fetch.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ b: 2 });
  });

  test("apiPut 使用 PUT 方法", async () => {
    global.fetch = jest.fn().mockResolvedValue(okJson({ ok: true }));
    await apiPut("/x", { c: 3 });
    expect(global.fetch.mock.calls[0][1].method).toBe("PUT");
  });

  test("apiUpload 用 FormData 上传文件", async () => {
    global.fetch = jest.fn().mockResolvedValue(okJson({ created: 1 }));
    const file = new File(["x"], "a.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await apiUpload("/api/data/import/vouchers", file);
    const [, init] = global.fetch.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
  });

  test("apiUpload 失败抛错", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "导入失败" }),
    });
    await expect(apiUpload("/x", new File(["x"], "a.xlsx"))).rejects.toThrow("导入失败");
  });
});

describe("年度 / 区间查询口径", () => {
  test("defaultRange 默认按当月", () => {
    const r = defaultRange();
    expect(r.mode).toBe("month");
    expect(r.month).toBe(curPeriod());
    expect(r.year).toBe(curPeriod().slice(0, 4));
    expect(r.from).toBe(`${curPeriod().slice(0, 4)}-01`);
    expect(r.to).toBe(curPeriod());
  });

  test("rangeQuery 三种口径", () => {
    expect(rangeQuery({ mode: "month", month: "2026-05" })).toBe("period=2026-05");
    expect(rangeQuery({ mode: "year", year: "2026" })).toBe("year=2026");
    expect(rangeQuery({ mode: "range", from: "2025-11", to: "2026-04" }))
      .toBe("from_period=2025-11&to_period=2026-04");
  });

  test("rangeFromTo 区间推导", () => {
    expect(rangeFromTo({ mode: "month", month: "2026-05" })).toEqual({ fp: "2026-05", tp: "2026-05" });
    expect(rangeFromTo({ mode: "year", year: "2026" })).toEqual({ fp: "2026-01", tp: "2026-12" });
    expect(rangeFromTo({ mode: "range", from: "2025-11", to: "2026-04" }))
      .toEqual({ fp: "2025-11", tp: "2026-04" });
  });

  test("rangeLabel 展示", () => {
    expect(rangeLabel({ mode: "year", year: "2026" })).toBe("2026 年度");
    expect(rangeLabel({ mode: "range", from: "2025-11", to: "2026-04" })).toBe("2025-11 ~ 2026-04");
    expect(rangeLabel({ mode: "month", month: "2026-05" })).toBe("2026-05");
  });
});
