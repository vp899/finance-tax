const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function apiUrl(path) {
  return API + path;
}

export async function apiGet(path) {
  const r = await fetch(API + path);
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
    headers: body ? { "Content-Type": "application/json" } : undefined,
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
  const r = await fetch(API + path, { method: "POST", body: fd });
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
  return API + path;
}

export function fmtMoney(v) {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtDate(d) {
  return d ? String(d).slice(0, 10) : "";
}

export function curPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
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
  const now = new Date();
  return {
    mode: "month",
    month: curPeriod(),
    year: String(now.getFullYear()),
    from: `${now.getFullYear()}-01`,
    to: curPeriod(),
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
