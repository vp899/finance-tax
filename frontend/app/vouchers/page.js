"use client";

import { useCallback, useEffect, useState } from "react";
import {
  apiGet, apiPost, apiDel, curPeriod, defaultRange, downloadUrl, fmtMoney,
  rangeFromTo, rangeQuery,
} from "@/lib/api";
import { Alert, Badge, Empty, Modal, PeriodRange, Tabs } from "@/components/ui";
import VoucherEditor from "@/components/VoucherEditor";

const STATUS = {
  posted: { label: "已记账", color: "green" },
  draft: { label: "草稿", color: "amber" },
  voided: { label: "已作废", color: "red" },
};

export default function VouchersPage() {
  const [tab, setTab] = useState("list");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">凭证管理</h1>
      <Tabs
        tabs={[
          { key: "list", label: "凭证列表" },
          { key: "summary", label: "凭证汇总表" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "list" ? <VoucherList /> : <VoucherSummary />}
    </div>
  );
}

function VoucherSummary() {
  const [range, setRange] = useState(defaultRange());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    const { fp, tp } = rangeFromTo(range);
    apiGet(`/api/vouchers/summary?from_period=${fp}&to_period=${tp}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [range]);

  useEffect(load, [load]);
  const { fp, tp } = rangeFromTo(range);

  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-3 p-4 border-b border-slate-200">
        <PeriodRange value={range} onChange={setRange} />
        <button className="btn-ghost" onClick={load}>查询</button>
        <div className="flex-1" />
        <a className="btn-ghost" href={downloadUrl(`/api/reports/export/voucher-summary?from_period=${fp}&to_period=${tp}`)}>
          导出 Excel
        </a>
      </div>
      {error && <div className="p-4"><Alert onClose={() => setError("")}>{error}</Alert></div>}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">凭证类型</th>
              <th className="th text-right">凭证张数</th>
              <th className="th text-right">借方合计</th>
              <th className="th text-right">贷方合计</th>
            </tr>
          </thead>
          <tbody>
            {data?.rows?.map((r) => (
              <tr key={r.vtype}>
                <td className="td">{r.vtype}</td>
                <td className="td-num">{r.count}</td>
                <td className="td-num">{fmtMoney(r.debit)}</td>
                <td className="td-num">{fmtMoney(r.credit)}</td>
              </tr>
            ))}
            {data && (
              <tr className="bg-slate-50 font-semibold">
                <td className="td">合计</td>
                <td className="td-num">{data.count}</td>
                <td className="td-num">{fmtMoney(data.total_debit)}</td>
                <td className="td-num">{fmtMoney(data.total_credit)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {data && !data.balanced && (
        <div className="p-4"><Alert>凭证汇总借贷不平衡，请检查凭证数据</Alert></div>
      )}
      {!data?.rows?.length && <Empty text="该期间暂无凭证" />}
    </div>
  );
}

function VoucherList() {
  const [range, setRange] = useState(defaultRange());
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ rows: [], total: 0 });
  const [error, setError] = useState("");
  const [editor, setEditor] = useState(null); // null | {} | voucher
  const [view, setView] = useState(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), size: "20" });
    if (range.mode === "month") params.set("period", range.month);
    else if (range.mode === "year") params.set("year", range.year);
    else {
      params.set("from_period", range.from);
      params.set("to_period", range.to);
    }
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    apiGet(`/api/vouchers?${params}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [range, status, q, page]);

  useEffect(load, [load]);

  const voidVoucher = async (v) => {
    if (!confirm(`确认${v.status === "voided" ? "恢复" : "作废"}凭证 ${v.voucher_no}？`)) return;
    try {
      await apiPost(`/api/vouchers/${v.id}/void`);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const copyVoucher = async (v) => {
    try {
      await apiPost(`/api/vouchers/${v.id}/copy`);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  const deleteVoucher = async (v) => {
    if (!confirm(`确认删除凭证 ${v.voucher_no}？删除后不可恢复（建议优先使用【作废】保留痕迹）。`)) return;
    try {
      const r = await apiDel(`/api/vouchers/${v.id}`);
      if (r.carryover_records_removed) {
        setError("");
      }
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="space-y-4">
      {error && <Alert onClose={() => setError("")}>{error}</Alert>}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3 p-4 border-b border-slate-200">
          <PeriodRange value={range} onChange={(v) => { setRange(v); setPage(1); }} />
          <select
            className="input w-36"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部状态</option>
            <option value="posted">已记账</option>
            <option value="draft">草稿</option>
            <option value="voided">已作废</option>
          </select>
          <input
            className="input w-56"
            placeholder="搜索凭证号 / 摘要 / 备注"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
          <button className="btn-ghost" onClick={load}>查询</button>
          <div className="flex-1" />
          <a
            className="btn-ghost"
            href={downloadUrl(`/api/data/export/vouchers?from_period=${rangeFromTo(range).fp}&to_period=${rangeFromTo(range).tp}`)}
          >
            导出 Excel
          </a>
          <button className="btn-primary" onClick={() => setEditor({})}>＋ 新增凭证</button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">凭证号</th>
                <th className="th">日期</th>
                <th className="th">摘要</th>
                <th className="th text-right">借方合计</th>
                <th className="th text-right">贷方合计</th>
                <th className="th">状态</th>
                <th className="th">来源</th>
                <th className="th text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((v) => (
                <tr key={v.id} className={`hover:bg-slate-50 ${v.status === "voided" ? "opacity-50" : ""}`}>
                  <td className="td">
                    <button
                      className="text-brand-600 hover:underline font-medium"
                      onClick={() => apiGet(`/api/vouchers/${v.id}`).then(setView)}
                    >
                      {v.voucher_no}
                    </button>
                  </td>
                  <td className="td">{v.date}</td>
                  <td className="td max-w-xs truncate">{v.first_summary || v.remark || "—"}</td>
                  <td className="td-num">{fmtMoney(v.total_debit)}</td>
                  <td className="td-num">{fmtMoney(v.total_credit)}</td>
                  <td className="td">
                    <Badge color={STATUS[v.status]?.color}>{STATUS[v.status]?.label}</Badge>
                  </td>
                  <td className="td text-xs text-slate-400">
                    {v.source === "carryover" ? "结转生成" : v.source === "import" ? "Excel 导入" : "手工录入"}
                  </td>
                  <td className="td text-right whitespace-nowrap">
                    <button className="text-brand-600 text-xs hover:underline mr-2"
                      onClick={() => apiGet(`/api/vouchers/${v.id}`).then((d) => setEditor(d))}>
                      查看/编辑
                    </button>
                    <button className="text-slate-500 text-xs hover:underline mr-2"
                      onClick={() => copyVoucher(v)}>
                      复制
                    </button>
                    <button
                      className={`text-xs hover:underline ${v.status === "voided" ? "text-emerald-600" : "text-rose-600"}`}
                      onClick={() => voidVoucher(v)}
                    >
                      {v.status === "voided" ? "恢复" : "作废"}
                    </button>
                    <button
                      className="text-rose-600 text-xs hover:underline ml-2"
                      onClick={() => deleteVoucher(v)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.rows.length && <Empty text="该条件下暂无凭证，点击右上角【新增凭证】开始记账" />}
        </div>

        <div className="flex items-center justify-between px-4 py-3 text-sm text-slate-500">
          <span>共 {data.total} 张凭证</span>
          <div className="flex gap-2">
            <button className="btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              上一页
            </button>
            <span className="px-2 py-1.5">第 {page} 页</span>
            <button
              className="btn-ghost btn-sm"
              disabled={page * 20 >= data.total}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      </div>

      <Modal
        open={!!editor}
        wide
        title={editor?.id ? `凭证 ${editor.voucher_no}` : "新增凭证"}
        onClose={() => setEditor(null)}
      >
        {editor && (
          <VoucherEditor
            voucher={editor.id ? editor : null}
            onCancel={() => setEditor(null)}
            onSaved={() => {
              setEditor(null);
              load();
            }}
          />
        )}
      </Modal>

      <Modal open={!!view} wide title={view ? `凭证 ${view.voucher_no}` : ""} onClose={() => setView(null)}>
        {view && (
          <div className="space-y-3">
            <div className="flex gap-6 text-sm text-slate-600">
              <span>日期：{view.date}</span>
              <span>类型：{view.vtype}</span>
              <span>
                状态：<Badge color={STATUS[view.status]?.color}>{STATUS[view.status]?.label}</Badge>
              </span>
              {view.remark && <span>备注：{view.remark}</span>}
            </div>
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">摘要</th>
                  <th className="th">科目</th>
                  <th className="th text-right">借方</th>
                  <th className="th text-right">贷方</th>
                </tr>
              </thead>
              <tbody>
                {view.entries.map((e) => (
                  <tr key={e.id}>
                    <td className="td">{e.summary}</td>
                    <td className="td">
                      <span className="font-mono text-xs text-slate-400 mr-2">{e.account_code}</span>
                      {e.account_name}
                    </td>
                    <td className="td-num">{e.debit ? fmtMoney(e.debit) : ""}</td>
                    <td className="td-num">{e.credit ? fmtMoney(e.credit) : ""}</td>
                  </tr>
                ))}
                <tr className="bg-slate-50 font-semibold">
                  <td className="td" colSpan={2}>合计</td>
                  <td className="td-num">{fmtMoney(view.total_debit)}</td>
                  <td className="td-num">{fmtMoney(view.total_credit)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  );
}
