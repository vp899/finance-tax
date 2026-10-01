"use client";

import { useCallback, useEffect, useState } from "react";
import {
  apiGet, curPeriod, defaultRange, downloadUrl, fmtMoney, rangeQuery,
} from "@/lib/api";
import { Alert, Badge, Empty, Money, PeriodRange, Tabs } from "@/components/ui";

const TABS = [
  { key: "general", label: "总账" },
  { key: "detail", label: "明细账" },
  { key: "balance", label: "余额表" },
  { key: "journal", label: "序时账" },
  { key: "multi", label: "多栏账" },
  { key: "trial", label: "试算平衡表" },
];

export default function BooksPage() {
  const [tab, setTab] = useState("general");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">账簿查询</h1>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "general" && <GeneralLedger />}
      {tab === "balance" && <BalanceTable />}
      {tab === "detail" && <DetailLedger />}
      {tab === "journal" && <Journal />}
      {tab === "multi" && <MultiColumn />}
      {tab === "trial" && <TrialBalance />}
    </div>
  );
}

function Bar({ children }) {
  return (
    <div className="card flex flex-wrap items-center gap-3 p-4 border-b border-slate-200">
      {children}
    </div>
  );
}

function AccountPicker({ value, onChange }) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    apiGet("/api/accounts").then((rows) => setItems(rows || [])).catch(() => {});
  }, []);
  return (
    <select className="input w-72" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">选择科目…</option>
      {items.map((a) => (
        <option key={a.id} value={a.code}>
          {"　".repeat(Math.max(0, a.level - 1))}
          {a.code} {a.name}
        </option>
      ))}
    </select>
  );
}

function GeneralLedger() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    apiGet(`/api/books/general-ledger?${rangeQuery(range)}`).then(setData).catch((e) => setError(e.message));
  }, [range]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/data/export/book/general-ledger?${rangeQuery(range)}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">科目</th>
              <th className="th text-right">期初余额</th>
              <th className="th text-right">本期借方</th>
              <th className="th text-right">本期贷方</th>
              <th className="th text-right">期末余额</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r) => {
              const opening = r.opening_debit || r.opening_credit;
              const closing = r.closing_debit || r.closing_credit;
              return (
                <tr key={r.code} className="hover:bg-slate-50">
                  <td className="td">
                    <span style={{ paddingLeft: (r.level - 1) * 16 }} className={r.level > 1 ? "text-slate-500" : "font-medium"}>
                      {r.code} {r.name}
                    </span>
                  </td>
                  <td className="td-num">
                    {opening ? <><Money v={opening} /> {r.opening_debit ? "借" : "贷"}</> : ""}
                  </td>
                  <td className="td-num">{r.period_debit ? <Money v={r.period_debit} /> : ""}</td>
                  <td className="td-num">{r.period_credit ? <Money v={r.period_credit} /> : ""}</td>
                  <td className="td-num font-medium">
                    {closing ? <><Money v={closing} /> {r.closing_debit ? "借" : "贷"}</> : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty />}
      </div>
    </div>
  );
}

function BalanceTable() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    apiGet(`/api/books/balance-table?${rangeQuery(range)}`).then(setData).catch((e) => setError(e.message));
  }, [range]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/data/export/book/balance-table?${rangeQuery(range)}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th" rowSpan={2}>科目</th>
              <th className="th text-center" colSpan={2}>期初余额</th>
              <th className="th text-center" colSpan={2}>本期发生额</th>
              <th className="th text-center" colSpan={2}>期末余额</th>
            </tr>
            <tr>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r) => (
              <tr key={r.code} className="hover:bg-slate-50">
                <td className="td">
                  <span style={{ paddingLeft: (r.level - 1) * 16 }}>{r.code} {r.name}</span>
                </td>
                <td className="td-num"><Money v={r.opening_debit} dim /></td>
                <td className="td-num"><Money v={r.opening_credit} dim /></td>
                <td className="td-num"><Money v={r.period_debit} dim /></td>
                <td className="td-num"><Money v={r.period_credit} dim /></td>
                <td className="td-num font-medium"><Money v={r.closing_debit} dim /></td>
                <td className="td-num font-medium"><Money v={r.closing_credit} dim /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty />}
      </div>
    </div>
  );
}

function DetailLedger() {
  const [code, setCode] = useState("1002");
  const [from, setFrom] = useState(`${curPeriod().slice(0, 4)}-01`);
  const [to, setTo] = useState(curPeriod());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    if (!code) return;
    apiGet(`/api/books/detail?account_code=${code}&from_period=${from}&to_period=${to}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [code, from, to]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <AccountPicker value={code} onChange={setCode} />
        <input type="month" className="input w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
        <span className="text-slate-400">至</span>
        <input type="month" className="input w-40" value={to} onChange={(e) => setTo(e.target.value)} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/detail?account_code=${code}&from_period=${from}&to_period=${to}`)}
        >
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      {data && (
        <div className="px-4 pt-3 text-sm text-slate-500">
          {data.account?.code} {data.account?.name} · 期初余额：
          {fmtMoney(data.opening.debit || data.opening.credit)} {data.opening.debit ? "借" : "贷"}
        </div>
      )}
      <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">日期</th>
              <th className="th">凭证号</th>
              <th className="th">摘要</th>
              <th className="th">科目</th>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
              <th className="th text-right">余额方向</th>
              <th className="th text-right">余额</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r, i) => (
              <tr key={i} className="hover:bg-slate-50">
                <td className="td">{r.date}</td>
                <td className="td">{r.voucher_no}</td>
                <td className="td">{r.summary}</td>
                <td className="td text-xs">
                  <span className="font-mono text-slate-400 mr-1">{r.account_code}</span>
                  {r.account_name}
                </td>
                <td className="td-num"><Money v={r.debit} dim /></td>
                <td className="td-num"><Money v={r.credit} dim /></td>
                <td className="td text-center text-xs">{r.balance_debit ? "借" : "贷"}</td>
                <td className="td-num font-medium">
                  <Money v={r.balance_debit || r.balance_credit} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty text="该科目在此期间无发生额" />}
      </div>
    </div>
  );
}

function Journal() {
  const [from, setFrom] = useState(`${curPeriod().slice(0, 4)}-01`);
  const [to, setTo] = useState(curPeriod());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    apiGet(`/api/books/journal?from_period=${from}&to_period=${to}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [from, to]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <input type="month" className="input w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
        <span className="text-slate-400">至</span>
        <input type="month" className="input w-40" value={to} onChange={(e) => setTo(e.target.value)} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/data/export/book/journal?from_period=${from}&to_period=${to}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">日期</th>
              <th className="th">凭证号</th>
              <th className="th">类型</th>
              <th className="th">摘要</th>
              <th className="th">科目</th>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
              <th className="th text-right">数量</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r, i) => (
              <tr key={i} className="hover:bg-slate-50">
                <td className="td">{r.date}</td>
                <td className="td">{r.voucher_no}</td>
                <td className="td text-xs text-slate-500">{r.vtype}</td>
                <td className="td">{r.summary}</td>
                <td className="td text-xs">
                  <span className="font-mono text-slate-400 mr-1">{r.account_code}</span>
                  {r.account_name}
                </td>
                <td className="td-num"><Money v={r.debit} dim /></td>
                <td className="td-num"><Money v={r.credit} dim /></td>
                <td className="td-num text-xs">{r.quantity || ""}</td>
              </tr>
            ))}
            {data && (
              <tr className="bg-slate-50 font-semibold">
                <td className="td" colSpan={5}>合计</td>
                <td className="td-num">{fmtMoney(data.total_debit)}</td>
                <td className="td-num">{fmtMoney(data.total_credit)}</td>
                <td className="td"></td>
              </tr>
            )}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty />}
      </div>
    </div>
  );
}

function TrialBalance() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    apiGet(`/api/books/trial-balance?${rangeQuery(range)}`).then(setData).catch((e) => setError(e.message));
  }, [range]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        {data && (
          data.balanced ? (
            <Badge color="green">试算平衡</Badge>
          ) : (
            <Badge color="red">试算不平衡 差额 {fmtMoney(data.difference)}</Badge>
          )
        )}
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/data/export/book/trial-balance?${rangeQuery(range)}`)}>
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">科目</th>
              <th className="th text-right">期初借方</th>
              <th className="th text-right">期初贷方</th>
              <th className="th text-right">本期借方</th>
              <th className="th text-right">本期贷方</th>
              <th className="th text-right">期末借方</th>
              <th className="th text-right">期末贷方</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r) => (
              <tr key={r.code} className="hover:bg-slate-50">
                <td className="td">
                  <span className={r.is_leaf === false ? "text-amber-600" : ""}>
                    {r.code} {r.name}{r.is_leaf === false ? "（非末级·直接记账）" : ""}
                  </span>
                </td>
                <td className="td-num"><Money v={r.opening_debit} dim /></td>
                <td className="td-num"><Money v={r.opening_credit} dim /></td>
                <td className="td-num"><Money v={r.period_debit} dim /></td>
                <td className="td-num"><Money v={r.period_credit} dim /></td>
                <td className="td-num"><Money v={r.debit} dim /></td>
                <td className="td-num"><Money v={r.credit} dim /></td>
              </tr>
            ))}
            {data && (
              <tr className="bg-slate-50 font-semibold">
                <td className="td">合计</td>
                <td className="td"></td>
                <td className="td"></td>
                <td className="td"></td>
                <td className="td"></td>
                <td className="td-num">{fmtMoney(data.total_debit)}</td>
                <td className="td-num">{fmtMoney(data.total_credit)}</td>
              </tr>
            )}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty />}
      </div>
    </div>
  );
}

function MultiColumn() {
  const [code, setCode] = useState("5602");
  const [from, setFrom] = useState(`${curPeriod().slice(0, 4)}-01`);
  const [to, setTo] = useState(curPeriod());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    if (!code) return;
    apiGet(`/api/books/multi-column?account_code=${code}&from_period=${from}&to_period=${to}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [code, from, to]);
  useEffect(load, [load]);

  return (
    <div className="card">
      <Bar>
        <AccountPicker value={code} onChange={setCode} />
        <input type="month" className="input w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
        <span className="text-slate-400">至</span>
        <input type="month" className="input w-40" value={to} onChange={(e) => setTo(e.target.value)} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/multi-column?account_code=${code}&from_period=${from}&to_period=${to}`)}
        >
          导出 Excel
        </a>
      </Bar>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">日期</th>
              <th className="th">凭证号</th>
              <th className="th">摘要</th>
              {data?.columns?.map((c) => (
                <th key={c.code} className="th text-right">{c.name}</th>
              ))}
              <th className="th text-right">合计</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r, i) => (
              <tr key={i} className="hover:bg-slate-50">
                <td className="td">{r.date}</td>
                <td className="td">{r.voucher_no}</td>
                <td className="td">{r.summary}</td>
                {data.columns.map((c) => (
                  <td key={c.code} className="td-num">
                    <Money v={r.columns[c.code]} dim />
                  </td>
                ))}
                <td className="td-num"><Money v={r.debit - r.credit} dim /></td>
              </tr>
            ))}
            {data?.rows?.length > 0 && (
              <tr className="bg-slate-50 font-semibold">
                <td className="td" colSpan={3}>合计</td>
                {data.columns.map((c) => (
                  <td key={c.code} className="td-num"><Money v={data.total[c.code]} dim /></td>
                ))}
                <td className="td-num">
                  {fmtMoney(Object.values(data.total).reduce((a, b) => a + b, 0))}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {!data?.rows?.length && <Empty text="该科目在此期间无发生额（多栏账以明细科目分栏）" />}
      </div>
    </div>
  );
}
