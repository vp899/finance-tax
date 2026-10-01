"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiUpload, curPeriod, downloadUrl, fmtMoney } from "@/lib/api";
import { Alert, Badge } from "@/components/ui";

export default function DataPage() {
  const [period, setPeriod] = useState(curPeriod());
  const [from, setFrom] = useState(`${curPeriod().slice(0, 4)}-01`);
  const [to, setTo] = useState(curPeriod());
  const [info, setInfo] = useState(null);
  const [msg, setMsg] = useState(null); // {type, text}
  const [busy, setBusy] = useState(false);
  const importRef = useRef(null);
  const restoreRef = useRef(null);

  const loadInfo = () => apiGet("/api/data/backup/info").then(setInfo).catch(() => {});
  useEffect(() => { loadInfo(); }, []);

  const doImport = async (file) => {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await apiUpload("/api/data/import/vouchers", file);
      setMsg({
        type: "success",
        text: `导入完成：成功生成 ${r.created} 张凭证` +
          (r.errors?.length ? `；跳过 ${r.errors.length} 条问题数据：${r.errors.slice(0, 3).join("；")}` : ""),
      });
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setBusy(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const doRestore = async (file) => {
    if (!file) return;
    if (!confirm("恢复备份将覆盖当前数据库，确定继续吗？")) {
      if (restoreRef.current) restoreRef.current.value = "";
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await apiUpload("/api/data/backup/restore", file);
      setMsg({ type: "success", text: `备份恢复成功（${fmtMoney(r.restored_bytes / 1024)} KB）` });
      loadInfo();
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setBusy(false);
      if (restoreRef.current) restoreRef.current.value = "";
    }
  };

  const books = [
    { key: "general-ledger", name: "总账", path: `/api/data/export/book/general-ledger?period=${period}` },
    { key: "balance-table", name: "余额表", path: `/api/data/export/book/balance-table?period=${period}` },
    { key: "detail", name: "明细账（1002 银行存款示例）", path: `/api/data/export/book/detail?account_code=1002&from_period=${from}&to_period=${to}` },
    { key: "journal", name: "序时账", path: `/api/data/export/book/journal?from_period=${from}&to_period=${to}` },
    { key: "multi", name: "多栏账（管理费用示例）", path: `/api/data/export/book/multi-column?account_code=5602&from_period=${from}&to_period=${to}` },
    { key: "trial", name: "试算平衡表", path: `/api/data/export/book/trial-balance?period=${period}` },
    { key: "vouchers", name: "凭证明细", path: `/api/data/export/vouchers?from_period=${from}&to_period=${to}` },
    { key: "vsum", name: "凭证汇总表", path: `/api/reports/export/voucher-summary?from_period=${from}&to_period=${to}` },
    { key: "bs", name: "资产负债表", path: `/api/reports/export/balance-sheet?period=${period}` },
    { key: "is", name: "利润表", path: `/api/reports/export/income?period=${period}&mode=month` },
    { key: "isq", name: "利润表季报", path: `/api/reports/export/income?period=${period}&mode=quarter` },
    { key: "cf", name: "现金流量表", path: `/api/reports/export/cashflow?from_period=${from}&to_period=${to}` },
  ];

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-slate-900">数据管理</h1>
      {msg && <Alert type={msg.type} onClose={() => setMsg(null)}>{msg.text}</Alert>}

      <div className="card p-5">
        <h2 className="font-semibold text-slate-800 mb-3">报表与账簿导出（Excel）</h2>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <span className="text-sm text-slate-500">期间</span>
          <input type="month" className="input w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
          <span className="text-sm text-slate-500">区间</span>
          <input type="month" className="input w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
          <span className="text-slate-400">至</span>
          <input type="month" className="input w-40" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="grid md:grid-cols-3 xl:grid-cols-4 gap-3">
          {books.map((b) => (
            <a
              key={b.key}
              href={downloadUrl(b.path)}
              className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5 hover:border-brand-400 hover:bg-brand-50/40 transition-colors"
            >
              <span className="text-sm">{b.name}</span>
              <span className="text-xs text-brand-600">下载</span>
            </a>
          ))}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="card p-5">
          <h2 className="font-semibold text-slate-800">凭证导入（Excel）</h2>
          <p className="text-sm text-slate-500 mt-2 leading-relaxed">
            按模板填写：日期、凭证类型、摘要、科目编码、借方金额、贷方金额、数量、单位。
            同一日期+类型的连续行合并为一张凭证，导入时自动校验借贷平衡与科目有效性。
          </p>
          <div className="flex gap-2 mt-4">
            <a className="btn-ghost" href={downloadUrl("/api/data/template/vouchers")}>
              下载导入模板
            </a>
            <label className="btn-primary cursor-pointer">
              {busy ? "处理中…" : "选择文件导入"}
              <input
                ref={importRef}
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={(e) => doImport(e.target.files?.[0])}
              />
            </label>
          </div>
        </div>

        <div className="card p-5">
          <h2 className="font-semibold text-slate-800">数据库备份与恢复</h2>
          <div className="text-sm text-slate-500 mt-2 space-y-1">
            <div>数据库文件：SQLite（单文件，可直接拷贝留存）</div>
            {info && (
              <>
                <div>大小：{fmtMoney(info.size_bytes / 1024)} KB</div>
                <div>最后修改：{info.created_at?.replace("T", " ").slice(0, 19)}</div>
              </>
            )}
          </div>
          <div className="flex gap-2 mt-4">
            <a className="btn-primary" href={downloadUrl("/api/data/backup/download")}>
              ⬇ 备份数据库
            </a>
            <label className="btn-ghost cursor-pointer">
              {busy ? "处理中…" : "从备份恢复"}
              <input
                ref={restoreRef}
                type="file"
                accept=".db"
                className="hidden"
                onChange={(e) => doRestore(e.target.files?.[0])}
              />
            </label>
          </div>
          <div className="mt-3 text-xs text-slate-400">
            恢复会覆盖当前全部数据，操作前请确认已下载最新备份。
          </div>
        </div>
      </div>
    </div>
  );
}
