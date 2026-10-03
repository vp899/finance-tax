"use client";

import { useCallback, useEffect, useState } from "react";
import {
  apiGet, curPeriod, defaultRange, downloadUrl, fmtMoney, rangeFromTo,
  rangeQuery,
} from "@/lib/api";
import { Alert, Badge, Empty, PeriodRange, Tabs, Amt } from "@/components/ui";

const TABS = [
  { key: "general-ledger", label: "总账" },
  { key: "balance-table", label: "余额表" },
  { key: "detail", label: "明细账" },
  { key: "journal", label: "序时账" },
  { key: "multi-column", label: "多栏账" },
  { key: "trial-balance", label: "试算平衡表" },
];

export default function BooksPage() {
  const [tab, setTab] = useState("general-ledger");
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">账簿查询</h1>
        <div className="text-xs text-slate-400">
          总账 / 余额表 / 明细账 / 序时账 / 多栏账 / 试算平衡表 · 支持按月 / 按年度 / 按起止区间
        </div>
      </div>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "general-ledger" && <LedgerTable kind="general-ledger" title="总账" />}
      {tab === "balance-table" && <LedgerTable kind="balance-table" title="余额表" />}
      {tab === "detail" && <DetailLedger />}
      {tab === "journal" && <Journal />}
      {tab === "multi-column" && <MultiColumn />}
      {tab === "trial-balance" && <TrialBalance />}
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

function ErrorBox({ error, onClose }) {
  return error ? (
    <div className="p-4">
      <Alert onClose={onClose}>{error}</Alert>
    </div>
  ) : null;
}

function AccountSelect({ accounts, value, onChange }) {
  return (
    <select className="input w-64" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">请选择科目</option>
      {accounts.map((a) => (
        <option key={a.code} value={a.code}>
          {a.code} {a.name}
        </option>
      ))}
    </select>
  );
}

function useAccounts() {
  const [accounts, setAccounts] = useState([]);
  useEffect(() => {
    apiGet("/api/accounts")
      .then((rows) => setAccounts(Array.isArray(rows) ? rows : []))
      .catch(() => setAccounts([]));
  }, []);
  return accounts;
}

/* ---------------- 总账 / 余额表 ---------------- */
function LedgerTable({ kind, title }) {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    apiGet(`/api/books/${kind}?${rangeQuery(range)}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [kind, range]);
  useEffect(load, [load]);

  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const { fp, tp } = rangeFromTo(range);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/${kind}?from_period=${fp}&to_period=${tp}`)}
        >
          导出 Excel
        </a>
      </Bar>
      <ErrorBox error={error} onClose={() => setError("")} />
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">科目编码</th>
              <th className="th">科目名称</th>
              <th className="th text-right">期初借方</th>
              <th className="th text-right">期初贷方</th>
              <th className="th text-right">本期借方</th>
              <th className="th text-right">本期贷方</th>
              <th className="th text-right">期末借方</th>
              <th className="th text-right">期末贷方</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code}>
                <td className="td">{r.code}</td>
                <td className="td">
                  <span style={{ paddingLeft: `${Math.max(0, (r.level || 1) - 1) * 14}px` }}>
                    {r.name}
                  </span>
                </td>
                <td className="td-num"><Amt v={r.opening_debit} /></td>
                <td className="td-num"><Amt v={r.opening_credit} /></td>
                <td className="td-num"><Amt v={r.period_debit} /></td>
                <td className="td-num"><Amt v={r.period_credit} /></td>
                <td className="td-num"><Amt v={r.closing_debit} /></td>
                <td className="td-num"><Amt v={r.closing_credit} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <Empty text={`${title}暂无数据（${rangeQuery(range)}）`} />}
      </div>
    </div>
  );
}

/* ---------------- 明细账 ---------------- */
function DetailLedger() {
  const [range, setRange] = useState(defaultRange());
  const [code, setCode] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const accounts = useAccounts();
  const { fp, tp } = rangeFromTo(range);

  const load = useCallback(() => {
    if (!code) return;
    setError("");
    apiGet(`/api/books/detail?account_code=${encodeURIComponent(code)}&from_period=${fp}&to_period=${tp}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [code, fp, tp]);
  useEffect(load, [load]);

  const rows = Array.isArray(data?.rows) ? data.rows : [];

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <AccountSelect accounts={accounts} value={code} onChange={setCode} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/detail?account_code=${code}&from_period=${fp}&to_period=${tp}`)}
        >
          导出 Excel
        </a>
      </Bar>
      <ErrorBox error={error} onClose={() => setError("")} />
      {code && data?.opening && (
        <div className="px-4 py-2 text-xs text-slate-500">
          期初余额：借 <Amt v={data.opening.debit} /> / 贷 <Amt v={data.opening.credit} />
          {data.account ? `　科目方向：${data.account.direction === "C" ? "贷方" : "借方"}` : ""}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">日期</th>
              <th className="th">凭证号</th>
              <th className="th">摘要</th>
              <th className="th">科目</th>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
              <th className="th text-right">余额借方</th>
              <th className="th text-right">余额贷方</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.voucher_no}-${i}`}>
                <td className="td">{r.date}</td>
                <td className="td">{r.source_no || r.voucher_no}</td>
                <td className="td">{r.summary}</td>
                <td className="td">{r.account_code} {r.account_name}</td>
                <td className="td-num"><Amt v={r.debit} /></td>
                <td className="td-num"><Amt v={r.credit} /></td>
                <td className="td-num"><Amt v={r.balance_debit} /></td>
                <td className="td-num"><Amt v={r.balance_credit} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <Empty text={code ? "该科目在所选区间内无发生额" : "请选择科目后查询明细账"} />}
      </div>
    </div>
  );
}

/* ---------------- 序时账 ---------------- */
function Journal() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { fp, tp } = rangeFromTo(range);

  const load = useCallback(() => {
    setError("");
    apiGet(`/api/books/journal?from_period=${fp}&to_period=${tp}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [fp, tp]);
  useEffect(load, [load]);

  const rows = Array.isArray(data?.rows) ? data.rows : [];

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/journal?from_period=${fp}&to_period=${tp}`)}
        >
          导出 Excel
        </a>
      </Bar>
      <ErrorBox error={error} onClose={() => setError("")} />
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">日期</th>
              <th className="th">凭证号</th>
              <th className="th">类型</th>
              <th className="th">摘要</th>
              <th className="th">科目编码</th>
              <th className="th">科目名称</th>
              <th className="th text-right">借方</th>
              <th className="th text-right">贷方</th>
              <th className="th text-right">数量</th>
              <th className="th">单位</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.voucher_no}-${i}`}>
                <td className="td">{r.date}</td>
                <td className="td">{r.source_no || r.voucher_no}</td>
                <td className="td">{r.vtype}</td>
                <td className="td">{r.summary}</td>
                <td className="td">{r.account_code}</td>
                <td className="td">{r.account_name}</td>
                <td className="td-num"><Amt v={r.debit} /></td>
                <td className="td-num"><Amt v={r.credit} /></td>
                <td className="td-num">{r.quantity ? fmtMoney(r.quantity) : ""}</td>
                <td className="td">{r.unit}</td>
              </tr>
            ))}
            {rows.length > 0 && (
              <tr>
                <td className="td font-semibold" colSpan={6}>合计</td>
                <td className="td-num font-semibold"><Amt v={data?.total_debit} /></td>
                <td className="td-num font-semibold"><Amt v={data?.total_credit} /></td>
                <td className="td" colSpan={2} />
              </tr>
            )}
          </tbody>
        </table>
        {!rows.length && <Empty text="序时账暂无数据" />}
      </div>
    </div>
  );
}

/* ---------------- 多栏账 ---------------- */
function MultiColumn() {
  const [range, setRange] = useState(defaultRange());
  const [code, setCode] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const accounts = useAccounts();
  const { fp, tp } = rangeFromTo(range);

  const load = useCallback(() => {
    if (!code) return;
    setError("");
    apiGet(`/api/books/multi-column?account_code=${encodeURIComponent(code)}&from_period=${fp}&to_period=${tp}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [code, fp, tp]);
  useEffect(load, [load]);

  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const cols = Array.isArray(data?.columns) ? data.columns : [];

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <AccountSelect accounts={accounts} value={code} onChange={setCode} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/multi-column?account_code=${code}&from_period=${fp}&to_period=${tp}`)}
        >
          导出 Excel
        </a>
      </Bar>
      <ErrorBox error={error} onClose={() => setError("")} />
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">日期</th>
              <th className="th">凭证号</th>
              <th className="th">摘要</th>
              <th className="th">科目</th>
              {cols.map((c) => (
                <th key={c.code} className="th text-right">{c.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.voucher_no}-${i}`}>
                <td className="td">{r.date}</td>
                <td className="td">{r.voucher_no}</td>
                <td className="td">{r.summary}</td>
                <td className="td">{r.account_name}</td>
                {cols.map((c) => (
                  <td key={c.code} className="td-num"><Amt v={r.columns?.[c.code]} /></td>
                ))}
              </tr>
            ))}
            {rows.length > 0 && cols.length > 0 && (
              <tr>
                <td className="td font-semibold" colSpan={4}>合计</td>
                {cols.map((c) => (
                  <td key={c.code} className="td-num font-semibold">
                    <Amt v={data?.total?.[c.code]} />
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
        {!rows.length && <Empty text={code ? "该科目在所选区间内无发生额" : "请选择科目后查询多栏账"} />}
      </div>
    </div>
  );
}

/* ---------------- 试算平衡表 ---------------- */
function TrialBalance() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    apiGet(`/api/books/trial-balance?${rangeQuery(range)}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [range]);
  useEffect(load, [load]);

  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const { fp, tp } = rangeFromTo(range);

  return (
    <div className="card">
      <Bar>
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        {data && (
          <Badge color={data.balanced ? "green" : "red"}>
            {data.balanced ? "试算平衡" : "试算不平衡"}
          </Badge>
        )}
        {data && !data.balanced && (
          <span className="text-xs text-rose-600">
            差额 <Amt v={data.difference} />（借方合计 − 贷方合计）
          </span>
        )}
        <div className="flex-1" />
        <a
          className="btn-ghost"
          href={downloadUrl(`/api/data/export/book/trial-balance?from_period=${fp}&to_period=${tp}`)}
        >
          导出 Excel
        </a>
      </Bar>
      <ErrorBox error={error} onClose={() => setError("")} />
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">科目编码</th>
              <th className="th">科目名称</th>
              <th className="th text-right">期初借方</th>
              <th className="th text-right">期初贷方</th>
              <th className="th text-right">本期借方</th>
              <th className="th text-right">本期贷方</th>
              <th className="th text-right">期末借方</th>
              <th className="th text-right">期末贷方</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code}>
                <td className="td">{r.code}</td>
                <td className="td">{r.is_leaf === false ? `${r.name}（非末级）` : r.name}</td>
                <td className="td-num"><Amt v={r.opening_debit} /></td>
                <td className="td-num"><Amt v={r.opening_credit} /></td>
                <td className="td-num"><Amt v={r.period_debit} /></td>
                <td className="td-num"><Amt v={r.period_credit} /></td>
                <td className="td-num"><Amt v={r.debit ?? r.closing_debit} /></td>
                <td className="td-num"><Amt v={r.credit ?? r.closing_credit} /></td>
              </tr>
            ))}
            {rows.length > 0 && (
              <tr>
                <td className="td font-semibold" colSpan={2}>合计</td>
                <td className="td" colSpan={2} />
                <td className="td" colSpan={2} />
                <td className="td-num font-semibold"><Amt v={data?.total_debit} /></td>
                <td className="td-num font-semibold"><Amt v={data?.total_credit} /></td>
              </tr>
            )}
          </tbody>
        </table>
        {!rows.length && <Empty text="试算平衡表暂无数据" />}
      </div>
    </div>
  );
}
