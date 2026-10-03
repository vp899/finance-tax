"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiUpload, curPeriod, downloadUrl, fmtMoney, useSelMonth } from "@/lib/api";
import { Alert, Badge, Amt } from "@/components/ui";

export default function DataPage() {
  const [period, setPeriod] = useSelMonth();
  const [from, setFrom] = useState(`${curPeriod().slice(0, 4)}-01`);
  const [to, setTo] = useState(curPeriod());
  const [detailAcc, setDetailAcc] = useState("");
  const [info, setInfo] = useState(null);
  const [msg, setMsg] = useState(null); // {type, text}
  const [detailMsg, setDetailMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [detailBusy, setDetailBusy] = useState(false);
  const importRef = useRef(null);
  const detailRef = useRef(null);
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
          (r.merged ? `；并入已有凭证 ${r.merged} 张` : "") +
          (r.skipped ? `；重复跳过 ${r.skipped} 张` : "") +
          (r.red_rows
            ? `；${r.red_rows} 行红字（负数）金额已原样入库`
            : "") +
          (r.errors?.length ? `；跳过 ${r.errors.length} 条问题数据：${r.errors.slice(0, 3).join("；")}` : ""),
      });
    } catch (e) {
      setMsg({ type: "error", text: e.message });
    } finally {
      setBusy(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const doDetailImport = async (file) => {
    if (!file) return;
    setDetailBusy(true);
    setDetailMsg(null);
    try {
      const r = await apiUpload("/api/data/import/detail-ledger", file);
      const parts = [
        `读取 ${r.rows} 行`,
        `生成凭证 ${r.created_vouchers} 张`,
        r.merged_vouchers ? `并入已有凭证 ${r.merged_vouchers} 张` : "",
        r.skipped_vouchers ? `重复跳过 ${r.skipped_vouchers} 张` : "",
        r.draft_vouchers ? `草稿待补齐 ${r.draft_vouchers} 张` : "",
        r.opening_rows ? `期初 ${r.opening_rows} 行（${r.opening_year} 年度）` : "",
        r.created_accounts?.length ? `自动新增科目 ${r.created_accounts.length} 个` : "",
        r.red_rows ? `红字（负数）金额 ${r.red_rows} 行原样入库` : "",
      ].filter(Boolean);
      setDetailMsg({
        type: r.errors?.length || r.draft_vouchers ? "warn" : "success",
        text: `导入完成：${parts.join("；")}` +
          (r.errors?.length ? `
错误：${r.errors.slice(0, 5).join("；")}` : "") +
          (r.warnings?.length ? `
提醒：${r.warnings.slice(0, 5).join("；")}` : ""),
      });
    } catch (e) {
      setDetailMsg({ type: "error", text: e.message });
    } finally {
      setDetailBusy(false);
      if (detailRef.current) detailRef.current.value = "";
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
    { key: "detail", name: "明细账", path: `/api/data/export/detail-ledger?account_code=${detailAcc}&from_period=${from}&to_period=${to}` },
    { key: "detail-old", name: "明细账（余额式，1002 示例）", path: `/api/data/export/book/detail?account_code=1002&from_period=${from}&to_period=${to}` },
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
          <span className="text-sm text-slate-500">明细账科目（可选）</span>
          <input className="input w-32" placeholder="留空=全部科目" value={detailAcc}
                 onChange={(e) => setDetailAcc(e.target.value.trim())} />
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
            按模板填写：凭证类别 凭证号 凭证日期 附单据数 摘要 科目编码 科目名称 借方金额 贷方金额
            项目编码 项目 客户编码 客户 供应商编码 供应商 部门编码 部门 员工编码 员工 存货编码 存货
            规格型号 数量 计量单位 单价 外币金额 币种 汇率 制单人 审核人。
            同一凭证号+日期的行合并为一张凭证（保留原凭证号），导入时自动校验借贷平衡与科目有效性；
            负数金额（红字）原样入库并红字展示，支持利息收入等负数记法；
            重复导入自动跳过，也可直接导入本系统导出的凭证明细。
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
          <h2 className="font-semibold text-slate-800">明细账导入（Excel / CSV）</h2>
          <p className="text-sm text-slate-500 mt-2 leading-relaxed">
            格式：序号 科目编码 科目 日期 凭证号 摘要 借方 贷方 方向 余额。
            期初行（日期只到年月或凭证号为“期初余额”）写入科目期初并设置期初年份；
            记账行按“日期+凭证号”合并生成凭证并保留原凭证号；重复导入自动跳过。
            若同一凭证只含单方科目，会先存为草稿，补齐对方科目再导入后自动转正式。
          </p>
          <div className="flex gap-2 mt-4">
            <a className="btn-ghost" href={downloadUrl("/api/data/template/detail-ledger")}>
              下载导入模板
            </a>
            <label className="btn-primary cursor-pointer">
              {detailBusy ? "处理中…" : "选择明细账导入"}
              <input
                ref={detailRef}
                type="file"
                accept=".xlsx,.xls,.csv,.txt"
                className="hidden"
                onChange={(e) => doDetailImport(e.target.files?.[0])}
              />
            </label>
          </div>
          {detailMsg && (
            <div className={`mt-3 text-xs whitespace-pre-wrap leading-relaxed ${
              detailMsg.type === "error" ? "text-rose-600"
                : detailMsg.type === "warn" ? "text-amber-600" : "text-emerald-600"}`}>
              {detailMsg.text}
            </div>
          )}
        </div>

        <div className="card p-5">
          <h2 className="font-semibold text-slate-800">数据库备份与恢复</h2>
          <div className="text-sm text-slate-500 mt-2 space-y-1">
            <div>数据库文件：SQLite（单文件，可直接拷贝留存）</div>
            {info && (
              <>
                <div>大小：<Amt v={info.size_bytes / 1024} /> KB</div>
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
