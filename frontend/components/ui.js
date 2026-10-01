"use client";

import { useEffect } from "react";

export function Modal({ open, title, onClose, children, wide }) {
  useEffect(() => {
    if (!open) return;
    const h = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 p-6 overflow-auto">
      <div className={`card w-full ${wide ? "max-w-5xl" : "max-w-xl"} my-8`}>
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 border-b border-slate-200 px-1">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`tab ${active === t.key ? "tab-active" : "tab-idle"}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Money({ v, dim }) {
  if (v === null || v === undefined || v === "") return <span className="text-slate-300">—</span>;
  const n = Number(v);
  return (
    <span className={`tabular-nums ${dim && Math.abs(n) < 0.005 ? "text-slate-300" : ""}`}>
      {n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
    </span>
  );
}

export function Badge({ children, color = "slate" }) {
  const colors = {
    slate: "bg-slate-100 text-slate-600",
    green: "bg-emerald-100 text-emerald-700",
    red: "bg-rose-100 text-rose-700",
    blue: "bg-brand-100 text-brand-700",
    amber: "bg-amber-100 text-amber-700",
  };
  return <span className={`badge ${colors[color] || colors.slate}`}>{children}</span>;
}

export function Empty({ text = "暂无数据" }) {
  return (
    <div className="py-14 text-center text-slate-400 text-sm">{text}</div>
  );
}

export function Alert({ type = "error", children, onClose }) {
  const colors =
    type === "error"
      ? "bg-rose-50 border-rose-200 text-rose-700"
      : type === "success"
      ? "bg-emerald-50 border-emerald-200 text-emerald-700"
      : "bg-brand-50 border-brand-200 text-brand-700";
  return (
    <div className={`border rounded-lg px-4 py-2.5 text-sm flex items-start justify-between gap-3 ${colors}`}>
      <div>{children}</div>
      {onClose && (
        <button onClick={onClose} className="opacity-60 hover:opacity-100">✕</button>
      )}
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
    </div>
  );
}

/* 年度 / 区间查询口径选择器
 * value: { mode: "month"|"year"|"range", month, year, from, to }
 */
export function PeriodRange({ value, onChange, showMonth = true }) {
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        className="input w-24"
        value={value.mode}
        onChange={(e) => set({ mode: e.target.value })}
      >
        {showMonth && <option value="month">按月</option>}
        <option value="year">按年度</option>
        <option value="range">按区间</option>
      </select>
      {value.mode === "month" && showMonth && (
        <input
          type="month"
          className="input w-40"
          value={value.month}
          onChange={(e) => set({ month: e.target.value })}
        />
      )}
      {value.mode === "year" && (
        <input
          type="number"
          className="input w-28"
          value={value.year}
          min="1991"
          max="2999"
          onChange={(e) => set({ year: e.target.value })}
        />
      )}
      {value.mode === "range" && (
        <>
          <input
            type="month"
            className="input w-36"
            value={value.from}
            onChange={(e) => set({ from: e.target.value })}
          />
          <span className="text-slate-400 text-sm">至</span>
          <input
            type="month"
            className="input w-36"
            value={value.to}
            onChange={(e) => set({ to: e.target.value })}
          />
        </>
      )}
    </div>
  );
}
