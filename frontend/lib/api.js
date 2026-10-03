const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

import { useCallback, useEffect, useState } from "react";

/* ---------- 账套（多套账） ----------
 * 当前账套 id 存在 localStorage，所有请求自动带上 X-Book-Id 头，
 * 下载链接自动附加 book_id 参数。
 */
const BOOK_KEY = "ft_book_id";

export function currentBookId() {
  if (typeof window === "undefined") return "default";
  return window.localStorage.getItem(BOOK_KEY) || "default";
}

export function setBookId(id) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(BOOK_KEY, id || "default");
  }
}

export function bookQuery(path = "") {
  const id = currentBookId();
  const q = `book_id=${encodeURIComponent(id)}`;
  return path + (path.includes("?") ? "&" : "?") + q;
}

function bookHeaders(extra) {
  return { "X-Book-Id": currentBookId(), ...(extra || {}) };
}

export function apiUrl(path) {
  return API + path;
}

export async function apiGet(path) {
  const r = await fetch(API + path, { headers: bookHeaders() });
  if (!r.ok) {
    let msg = `请求失败 (${r.status})`;
    try {
      const j = await r.json();
      msg = j.detail || msg;
    } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

export async function apiSend(method, path, body) {
  const r = await fetch(API + path, {
    method,
    headers: bookHeaders(body ? { "Content-Type": "application/json" } : {}),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = `请求失败 (${r.status})`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : msg;
    } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

export const apiPost = (path, body) => apiSend("POST", path, body);
export const apiPut = (path, body) => apiSend("PUT", path, body);
export const apiDel = (path) => apiSend("DELETE", path);

export async function apiUpload(path, file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(API + path, { method: "POST", headers: bookHeaders(), body: fd });
  if (!r.ok) {
    let msg = `上传失败 (${r.status})`;
    try {
      const j = await r.json();
      msg = j.detail || msg;
    } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
}

export function downloadUrl(path) {
  return API + bookQuery(path);
}

export function fmtMoney(v) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/* 小数位规则：数量/单价最多 2 位（不足补零），汇率最多 6 位 */
export function fmtQty(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toFixed(dp);
}

export function fmtPrice(v, dp = 2) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toFixed(dp);
}

export function fmtRate(v, dp = 6) {
  if (v === null || v === undefined || v === "") return "";
  return String(Number(Number(v).toFixed(dp)));
}

/* 数量/单价输入过滤：最多 dp 位小数 */
export function limitDecimals(value, dp = 2) {
  const s = String(value).replace(/[^\d.]/g, "");
  const parts = s.split(".");
  return parts.length > 1 ? `${parts[0]}.${parts[1].slice(0, dp)}` : parts[0];
}

export function fmtDate(d) {
  return d ? String(d).slice(0, 10) : "";
}

export function realPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/* ---------- 选中月份（全局同步月份数据） ----------
 * 前端所有页面针对选中月份同步月份数据：任一处修改选中月份后，
 * 仪表盘 / 凭证 / 账簿 / 报表 / 结转 / 数据管理都以该月份为默认查询期间并自动刷新。
 */
const MONTH_KEY = "finance.selMonth";
const MONTH_EVENT = "finance:month-changed";

export function selMonth() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(MONTH_KEY) || "";
}

export function setSelMonth(month) {
  if (typeof window === "undefined") return;
  if (month) window.localStorage.setItem(MONTH_KEY, month);
  else window.localStorage.removeItem(MONTH_KEY);
  window.dispatchEvent(new Event(MONTH_EVENT));
}

/** 订阅选中月份变化（返回取消订阅函数），用于各页面同步月份数据 */
export function onMonthChange(handler) {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(MONTH_EVENT, handler);
  return () => window.removeEventListener(MONTH_EVENT, handler);
}

/** 选中月份（未设置时为当前自然月） */
export function curPeriod() {
  return selMonth() || realPeriod();
}

/** [选中月份, 修改选中月份]；修改后全局页面同步刷新月份数据 */
export function useSelMonth() {
  const [month, setMonthState] = useState(() => curPeriod());
  useEffect(() => onMonthChange(() => setMonthState(curPeriod())), []);
  const setMonth = useCallback((m) => {
    setSelMonth(m);
    setMonthState(m || realPeriod());
  }, []);
  return [month, setMonth];
}

export function shiftPeriod(period, delta) {
  let y = Number(period.slice(0, 4));
  let m = Number(period.slice(5, 7)) + delta;
  while (m > 12) { m -= 12; y += 1; }
  while (m < 1) { m += 12; y -= 1; }
  return `${y}-${String(m).padStart(2, "0")}`;
}

/* ---------- 年度 / 区间查询口径 ----------
 * value: { mode: "month" | "year" | "range", month, year, from, to }
 * rangeQuery(value) → 附加到 API 的查询参数字符串
 */
export function defaultRange() {
  const month = curPeriod();
  return {
    mode: "month",
    month,
    year: month.slice(0, 4),
    from: `${month.slice(0, 4)}-01`,
    to: month,
  };
}

export function rangeQuery(value) {
  if (value.mode === "year") return `year=${value.year}`;
  if (value.mode === "range") return `from_period=${value.from}&to_period=${value.to}`;
  return `period=${value.month}`;
}

export function rangeLabel(value) {
  if (value.mode === "year") return `${value.year} 年度`;
  if (value.mode === "range") return `${value.from} ~ ${value.to}`;
  return value.month;
}

export function rangeFromTo(value) {
  if (value.mode === "year") return { fp: `${value.year}-01`, tp: `${value.year}-12` };
  if (value.mode === "range") return { fp: value.from, tp: value.to };
  return { fp: value.month, tp: value.month };
}
