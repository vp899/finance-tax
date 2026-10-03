"use client";

import { useCallback, useEffect, useState } from "react";
import {
  apiGet, curPeriod, defaultRange, downloadUrl, fmtMoney, rangeFromTo,
} from "@/lib/api";
import { Alert, Badge, Empty, Money, PeriodRange, Tabs } from "@/components/ui";

const TABS = [
  { key: "bs", label: "资产负债表" },
  { key: "is", label: "利润表" },
  { key: "isq", label: "利润表季报" },
  { key: "cf", label: "现金流量表" },
  { key: "cfq", label: "现金流量表季报" },
];

export default function ReportsPage() {
  const [tab, setTab] = useState("bs");
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">财务报表</h1>
        <div className="text-xs text-slate-400">单位：元 · 小企业会计准则</div>
      </div>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "bs" && <BalanceSheet />}
      {tab === "is" && <Income mode="month" title="利润表" />}
      {tab === "isq" && <Income mode="quarter" title="利润表季报" />}
      {tab === "cf" && <Cashflow quarter={false} />}
      {tab === "cfq" && <Cashflow quarter={true} />}
    </div>
  );
}

function Bar({ children }) {
  return <div className="card flex flex-wrap items-center gap-3 p-4 border-b border-slate-200">{children}</div>;
}

function BalanceSheet() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { fp, tp } = rangeFromTo(range);
  const load = useCallback(() => {
    setError("");
    const q = range.mode === "year" ? `year=${range.year}` : `period=${tp}`;
    apiGet(`/api/reports/balance-sheet?${q}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [range]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>生成报表</button>
        {data && (
          <Badge color={data.balanced ? "green" : "red"}>
            {data.balanced ? "✓ 表内平衡" : "不平衡：资产 ≠ 负债+权益"}
          </Badge>
        )}
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/reports/export/balance-sheet?period=${tp}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">资产</th>
              <th className="th text-right">期末余额</th>
              <th className="th text-right">年初余额</th>
              <th className="th">负债和所有者权益</th>
              <th className="th text-right">期末余额</th>
              <th className="th text-right">年初余额</th>
            </tr>
          </thead>
          <tbody>
            <BSRows data={data} />
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BSRows({ data }) {
  if (!data) return null;
  const left = data.rows.filter((r) => r.group?.startsWith("asset"));
  const right = data.rows.filter((r) => !r.group?.startsWith("asset"));
  const n = Math.max(left.length, right.length);
  const cell = (r, side) => {
    if (!r) return [<td key={side + "a"} className="td"></td>, <td key={side + "b"} className="td"></td>, <td key={side + "c"} className="td"></td>];
    const bold = r.type !== "line";
    return [
      <td key={side + "a"} className={`td ${bold ? "font-semibold bg-slate-50" : ""}`}>{r.name}</td>,
      <td key={side + "b"} className={`td-num ${bold ? "font-semibold bg-slate-50" : ""}`}>
        <Money v={r.ending} dim={!bold} />
      </td>,
      <td key={side + "c"} className={`td-num ${bold ? "font-semibold bg-slate-50" : ""}`}>
        <Money v={r.beginning} dim={!bold} />
      </td>,
    ];
  };
  const rows = [];
  for (let i = 0; i < n; i++) {
    rows.push(
      <tr key={i} className="hover:bg-brand-50/30">
        {cell(left[i], "l")}
        {cell(right[i], "r")}
      </tr>
    );
  }
  return rows;
}

function Income({ mode, title }) {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { fp, tp } = rangeFromTo(range);
  const effMode = range.mode === "month" ? mode : "range";
  const load = useCallback(() => {
    setError("");
    const q = range.mode === "month"
      ? `period=${range.month}&mode=${mode}`
      : range.mode === "year"
        ? `year=${range.year}`
        : `from_period=${range.from}&to_period=${range.to}`;
    apiGet(`/api/reports/income?${q}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [range, mode]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>生成报表</button>
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/reports/export/income?period=${tp}&mode=${effMode}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">项目</th>
              <th className="th text-right">
                {effMode === "range" ? "区间金额" : mode === "quarter" ? "本季金额" : "本月金额"}
              </th>
              <th className="th text-right">本年累计金额</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r) => (
              <tr key={r.name} className={r.type === "calc" ? "bg-slate-50 font-semibold" : "hover:bg-slate-50"}>
                <td className="td whitespace-pre">{r.name}</td>
                <td className="td-num"><Money v={r.current} dim={r.type !== "calc"} /></td>
                <td className="td-num"><Money v={r.ytd} dim={r.type !== "calc"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty />}
      </div>
    </div>
  );
}

function Cashflow({ quarter }) {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const bounds = useCallback(() => {
    if (range.mode === "year") return { from: `${range.year}-01`, to: `${range.year}-12` };
    if (range.mode === "range") return { from: range.from, to: range.to };
    const period = range.month;
    const y = period.slice(0, 4);
    if (quarter) {
      const q = Math.floor((Number(period.slice(5, 7)) - 1) / 3);
      return { from: `${y}-${String(q * 3 + 1).padStart(2, "0")}`, to: period };
    }
    return { from: `${y}-01`, to: period };
  }, [range, quarter]);

  const load = useCallback(() => {
    setError("");
    const { from, to } = bounds();
    apiGet(`/api/reports/cashflow?from_period=${from}&to_period=${to}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [bounds]);
  useEffect(load, [load]);

  const { from, to } = bounds();
  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>生成报表</button>
        <span className="text-xs text-slate-400">区间 {from} 至 {to}</span>
        {data && (
          <Badge color={data.balanced ? "green" : "red"}>
            {data.balanced ? "✓ 与账面现金一致" : `期末差异 ${fmtMoney(data.difference ?? 0)}`}
          </Badge>
        )}
        {data && !data.balanced && (
          <span className="text-xs text-slate-500">
            表内期末 {fmtMoney(data.rows?.find((r) => r.name === "期末现金及现金等价物余额")?.amount)}
            　·　账面现金 {fmtMoney(data.book_ending_cash)}
          </span>
        )}
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/reports/export/cashflow?from_period=${from}&to_period=${to}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">项目</th>
              <th className="th text-right">金额</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r) => (
              <tr key={r.name} className={r.type !== "line" ? "bg-slate-50 font-semibold" : "hover:bg-slate-50"}>
                <td className="td">{r.name}</td>
                <td className="td-num"><Money v={r.amount} dim={r.type === "line"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty />}
      </div>
    </div>
  );
}
