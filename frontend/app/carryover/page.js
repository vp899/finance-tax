"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, apiPut, curPeriod, fmtMoney } from "@/lib/api";
import { Alert, Badge, Empty, Modal, PeriodRange, rangeQuery } from "@/components/ui";

const STATUS_COLOR = { created: "green", skipped: "amber", failed: "red", disabled: "slate" };

export default function CarryoverPage() {
  const [period, setPeriod] = useState(curPeriod());
  const [op, setOp] = useState(null);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [records, setRecords] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [kinds, setKinds] = useState([]);
  const [reload, setReload] = useState(0);
  const [runAllOpen, setRunAllOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [range, setRange] = useState(null);

  const load = useCallback(() => {
    const q = range ? rangeQuery(range) : `period=${period}`;
    apiGet(`/api/carryover/records?${q}`).then(setRecords).catch(() => {});
    apiGet("/api/carryover/periods").then(setPeriods).catch(() => {});
    apiGet("/api/carryover/kinds").then(setKinds).catch(() => {});
  }, [period, range]);
  useEffect(load, [load, reload]);

  const closePeriod = async (force) => {
    if (!confirm(`确认${force ? "强制" : ""}结账 ${period}？结账后该期间凭证不可修改。`)) return;
    setError("");
    setOk("");
    try {
      await apiPost("/api/carryover/close", { period, force });
      setOk(`${period} 结账成功`);
      setReload((r) => r + 1);
    } catch (e) {
      setError(e.message);
    }
  };

  const openPeriod = async () => {
    if (!confirm(`确认反结账 ${period}？`)) return;
    setError("");
    setOk("");
    try {
      await apiPost("/api/carryover/open", { period });
      setOk(`${period} 已反结账，可继续录入凭证`);
      setReload((r) => r + 1);
    } catch (e) {
      setError(e.message);
    }
  };

  const reverse = async (rec) => {
    if (!confirm(`确认反结转【${rec.kind_name || rec.kind}】凭证 ${rec.voucher_no}？该凭证将被作废。`)) return;
    setError("");
    setOk("");
    try {
      const r = await apiPost(`/api/carryover/reverse/${rec.id}`);
      setOk(`已反结转：${r.kind}（凭证 ${r.voucher_no} 已作废）`);
      setReload((x) => x + 1);
    } catch (e) {
      setError(e.message);
    }
  };

  const cur = periods.find((p) => p.period === period);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">结转与结账</h1>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="month"
            className="input w-44"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          />
          {cur && (
            <Badge color={cur.status === "closed" ? "red" : "green"}>
              {cur.status === "closed" ? `已结账 ${cur.closed_at?.slice(0, 10) || ""}` : "已开启"}
            </Badge>
          )}
          <button className="btn-ghost" onClick={() => setConfigOpen(true)}>结转配置</button>
          <button className="btn-primary" onClick={() => setRunAllOpen(true)}>⚡ 一键结转</button>
        </div>
      </div>

      {error && <Alert onClose={() => setError("")}>{error}</Alert>}
      {ok && <Alert type="success" onClose={() => setOk("")}>{ok}</Alert>}

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {(Array.isArray(kinds) ? kinds : []).map((o) => (
          <button
            key={o.kind}
            onClick={() => {
              setError("");
              setOp(o);
            }}
            className={`card p-4 text-left hover:shadow-md hover:border-brand-300 transition-all ${
              o.enabled ? "" : "opacity-50"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">
                {o.amount_mode === "auto" ? "自动计算" : o.amount_mode === "last" ? "按上期金额" : "录入金额"}
              </span>
              {!o.enabled && <Badge>已停用</Badge>}
            </div>
            <div className="mt-2 font-semibold text-slate-800">{o.name}</div>
            <div className="text-xs text-slate-500 mt-1 leading-relaxed">{o.desc}</div>
          </button>
        ))}
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-slate-200">
          <h2 className="font-semibold text-slate-800">结转记录</h2>
          <div className="flex flex-wrap items-center gap-2">
            <PeriodRange
              value={range || { mode: "month", month: period, year: period.slice(0, 4), from: `${period.slice(0, 4)}-01`, to: period }}
              onChange={(v) => setRange(v.mode === "month" ? null : v)}
            />
            <div className="flex gap-2">
              {cur?.status === "closed" ? (
                <button className="btn-ghost" onClick={openPeriod}>反结账</button>
              ) : (
                <>
                  <button className="btn-ghost" onClick={() => closePeriod(true)}>强制结账</button>
                  <button className="btn-primary" onClick={() => closePeriod(false)}>结账</button>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">期间</th>
                <th className="th">结转类型</th>
                <th className="th">凭证号</th>
                <th className="th text-right">金额</th>
                <th className="th">状态</th>
                <th className="th">生成时间</th>
                <th className="th">备注</th>
                <th className="th text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className={r.status === "reversed" ? "opacity-50" : "hover:bg-slate-50"}>
                  <td className="td">{r.period}</td>
                  <td className="td">{r.kind_name || r.kind}</td>
                  <td className="td">{r.voucher_no}</td>
                  <td className="td-num">{fmtMoney(r.amount)}</td>
                  <td className="td">
                    <Badge color={r.status === "active" ? "green" : "red"}>
                      {r.status === "active" ? "有效" : "已反结转"}
                    </Badge>
                  </td>
                  <td className="td text-xs text-slate-400">{r.created_at}</td>
                  <td className="td text-xs text-slate-500 max-w-xs truncate">{r.note}</td>
                  <td className="td text-right">
                    {r.status === "active" && (
                      <button className="text-rose-600 text-xs hover:underline" onClick={() => reverse(r)}>
                        反结转
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!records.length && <Empty text="该条件下暂无结转记录" />}
        </div>
        <div className="px-5 py-3 text-xs text-slate-400 border-t border-slate-100 leading-relaxed">
          结账检查：试算平衡 → 无草稿凭证 → 本期损益已结平。如需跳过损益检查请使用【强制结账】。
          反结转会作废对应结转凭证，报表金额自动回退。【一键结转】按结转配置的顺序执行全部启用步骤，金额为 0 或不适用的步骤自动跳过。
        </div>
      </div>

      {op && (
        <OpDialog
          op={op}
          period={period}
          onClose={() => setOp(null)}
          onDone={(msg) => {
            setOp(null);
            setOk(msg);
            setReload((x) => x + 1);
          }}
          onError={(msg) => setError(msg)}
        />
      )}

      {runAllOpen && (
        <RunAllDialog
          period={period}
          onClose={() => setRunAllOpen(false)}
          onDone={(msg) => {
            setRunAllOpen(false);
            setOk(msg);
            setReload((x) => x + 1);
          }}
          onError={(msg) => setError(msg)}
        />
      )}

      {configOpen && (
        <ConfigDialog
          onClose={() => setConfigOpen(false)}
          onSaved={() => {
            setConfigOpen(false);
            setOk("结转配置已保存");
            setReload((x) => x + 1);
          }}
          onError={(msg) => setError(msg)}
        />
      )}
    </div>
  );
}

/* ---------- 单个结转对话框 ---------- */

function usePreview(kind, period, extra) {
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [key, setKey] = useState(0);
  useEffect(() => {
    setPreview(null);
    setError("");
    const q = new URLSearchParams({ period });
    if (extra?.withheld !== undefined && extra.withheld !== "") q.set("withheld", extra.withheld);
    if (extra?.vat_base !== undefined && extra.vat_base !== "") q.set("vat_base", extra.vat_base);
    apiGet(`/api/carryover/preview/${kind}?${q}`)
      .then(setPreview)
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, period, key]);
  return { preview, error, reload: () => setKey((k) => k + 1) };
}

function OpDialog({ op, period, onClose, onDone, onError }) {
  const [amount, setAmount] = useState("");
  const [withheld, setWithheld] = useState("0");
  const [vatBase, setVatBase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [extra, setExtra] = useState({});
  const { preview, error: pErr } = usePreview(op.kind, period, extra);

  const isPay = ["pay_salary", "pay_bonus", "pay_labor"].includes(op.kind);
  const hasManualAmount = op.manual_amount || ["income_tax", "vat_free", "tax", "water_fund", "stamp_tax", "union_fee", "sales_cost", "salary"].includes(op.kind);

  useEffect(() => {
    if (!preview) return;
    if (op.kind === "sales_cost" || op.kind === "salary" || op.kind === "accrue_bonus" || op.kind === "accrue_labor" || op.kind === "amortize_deferred") {
      setAmount(String(preview.suggested_amount ?? preview.amount ?? ""));
    } else if (op.kind === "income_tax" || op.kind === "vat_free") {
      setAmount(String(preview.amount ?? ""));
    } else if (op.kind === "water_fund" || op.kind === "stamp_tax" || op.kind === "union_fee") {
      setAmount(String(preview.suggested_amount ?? ""));
    } else if (isPay) {
      setAmount(String(preview.suggested_amount ?? ""));
    } else if (op.kind === "tax") {
      setVatBase(String(preview.vat_base ?? ""));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview]);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const body = { period };
      if (hasManualAmount && amount !== "") body.amount = Number(amount) || 0;
      if (isPay) {
        if (amount !== "") body.amount = Number(amount) || 0;
        body.withheld = Number(withheld) || 0;
      }
      if (op.kind === "tax" && vatBase !== "") body.vat_base = Number(vatBase) || 0;
      const r = await apiPost(`/api/carryover/${op.kind}`, body);
      onDone(`${op.name}完成，生成凭证 ${r.voucher_no}，金额 ${fmtMoney(r.amount)}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={`${op.name} — ${period}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="text-sm text-slate-500 bg-slate-50 rounded-lg px-4 py-2.5">{op.desc}</div>
        {(error || pErr) && <Alert>{error || pErr}</Alert>}

        {preview?.skip && <Alert type="info">{preview.skip}</Alert>}

        {preview?.items?.length > 0 && (
          <div className="text-sm space-y-2">
            {preview.items.map((it, i) => (
              <div key={i} className="flex justify-between border-b border-dashed py-1">
                <span>{it.name || it.code}</span>
                <span className="tabular-nums">{fmtMoney(it.amount ?? it.diff)}</span>
              </div>
            ))}
            {preview.total !== undefined && (
              <div className="flex justify-between font-semibold">
                <span>合计</span>
                <span>{fmtMoney(preview.total)}</span>
              </div>
            )}
          </div>
        )}

        {preview?.lines_preview?.length > 0 && (
          <div className="max-h-72 overflow-auto border border-slate-200 rounded-lg">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">科目</th>
                  <th className="th">摘要</th>
                  <th className="th text-right">借方</th>
                  <th className="th text-right">贷方</th>
                </tr>
              </thead>
              <tbody>
                {preview.lines_preview.map((l, i) => (
                  <tr key={i}>
                    <td className="td">
                      <span className="font-mono text-xs text-slate-400 mr-2">{l.code}</span>
                      {l.name}
                    </td>
                    <td className="td text-xs text-slate-500">{l.summary}</td>
                    <td className="td-num">{l.debit ? fmtMoney(l.debit) : ""}</td>
                    <td className="td-num">{l.credit ? fmtMoney(l.credit) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {op.kind === "tax" && preview && (
          <div className="text-sm space-y-2">
            <label className="label">计税基数（本期应交增值税）</label>
            <input className="input" value={vatBase} onChange={(e) => setVatBase(e.target.value)} />
            <div className="grid grid-cols-3 gap-2 pt-1">
              <div className="bg-slate-50 rounded-lg p-2.5">
                <div className="text-xs text-slate-500">城建税 {(preview.rates.city * 100).toFixed(0)}%</div>
                <div className="font-semibold">{fmtMoney(preview.city_tax)}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2.5">
                <div className="text-xs text-slate-500">教育费附加 {(preview.rates.edu * 100).toFixed(0)}%</div>
                <div className="font-semibold">{fmtMoney(preview.edu_tax)}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2.5">
                <div className="text-xs text-slate-500">地方教育附加 {(preview.rates.local_edu * 100).toFixed(0)}%</div>
                <div className="font-semibold">{fmtMoney(preview.local_edu_tax)}</div>
              </div>
            </div>
          </div>
        )}

        {hasManualAmount && op.kind !== "tax" && (
          <div>
            <label className="label">结转金额（可修改）</label>
            <input className="input" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </div>
        )}

        {isPay && (
          <div>
            <label className="label">代扣个人所得税</label>
            <input className="input" value={withheld} onChange={(e) => setWithheld(e.target.value)} placeholder="0.00" />
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={run} disabled={busy}>
            {busy ? "处理中…" : `确认${op.name}`}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ---------- 一键结转 ---------- */

function RunAllDialog({ period, onClose, onDone, onError }) {
  const [steps, setSteps] = useState(null);
  const [amounts, setAmounts] = useState({});
  const [checked, setChecked] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState(null);

  useEffect(() => {
    apiGet("/api/carryover/kinds").then(async (kinds) => {
      const enabled = kinds.filter((k) => k.enabled);
      const previews = await Promise.all(
        enabled.map((k) =>
          apiGet(`/api/carryover/preview/${k.kind}?period=${period}`).catch(() => ({}))
        )
      );
      const rows = enabled.map((k, i) => {
        const p = previews[i] || {};
        const suggested = p.amount ?? p.suggested_amount ?? 0;
        return { ...k, suggested, skip: p.skip };
      });
      setSteps(rows);
      const ck = {};
      const am = {};
      rows.forEach((r) => {
        ck[r.kind] = !r.skip;
        if (r.suggested) am[r.kind] = String(r.suggested);
      });
      setChecked(ck);
      setAmounts(am);
    }).catch((e) => setError(e.message));
  }, [period]);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const kinds = steps.filter((s) => checked[s.kind]).map((s) => s.kind);
      const am = {};
      kinds.forEach((k) => {
        if (amounts[k] !== undefined && amounts[k] !== "") am[k] = Number(amounts[k]) || 0;
      });
      const r = await apiPost("/api/carryover/run-all", { period, kinds, amounts: am });
      setResults(r.results);
      if (!r.results.some((x) => x.status === "created")) {
        setError("没有可执行的结转步骤（金额为 0 或不适用）");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const finish = () => {
    const created = (results || []).filter((x) => x.status === "created");
    const failed = (results || []).filter((x) => x.status === "failed");
    let msg = `一键结转完成：生成 ${created.length} 张凭证`;
    if (failed.length) msg += `，失败 ${failed.length} 项（${failed.map((f) => f.name).join("、")}）`;
    onDone(msg);
  };

  return (
    <Modal open wide title={`一键结转 — ${period}`} onClose={onClose}>
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {!steps && !error && <div className="text-sm text-slate-40">加载中…</div>}

        {steps && !results && (
          <>
            <div className="text-xs text-slate-500">
              按结转配置顺序执行以下步骤；金额可修改，不适用的步骤已自动取消勾选。
            </div>
            <div className="max-h-[55vh] overflow-auto border border-slate-200 rounded-lg">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="th w-10"></th>
                    <th className="th">步骤</th>
                    <th className="th">分录</th>
                    <th className="th text-right">金额</th>
                    <th className="th">说明</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map((s) => (
                    <tr key={s.kind} className={checked[s.kind] ? "" : "opacity-50"}>
                      <td className="td text-center">
                        <input
                          type="checkbox"
                          checked={!!checked[s.kind]}
                          disabled={!!s.skip}
                          onChange={(e) => setChecked({ ...checked, [s.kind]: e.target.checked })}
                        />
                      </td>
                      <td className="td whitespace-nowrap">{s.name}</td>
                      <td className="td text-xs text-slate-500">{s.desc}</td>
                      <td className="td p-1">
                        <input
                          className="input text-right tabular-nums"
                          value={amounts[s.kind] ?? ""}
                          disabled={!!s.skip}
                          onChange={(e) => setAmounts({ ...amounts, [s.kind]: e.target.value.replace(/[^\d.]/g, "") })}
                        />
                      </td>
                      <td className="td text-xs text-slate-400">{s.skip || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={onClose}>取消</button>
              <button className="btn-primary" onClick={run} disabled={busy}>
                {busy ? "执行中…" : "执行一键结转"}
              </button>
            </div>
          </>
        )}

        {results && (
          <>
            <table className="w-full">
              <thead>
                <tr>
                  <th className="th">步骤</th>
                  <th className="th">结果</th>
                  <th className="th text-right">金额</th>
                  <th className="th">凭证号</th>
                  <th className="th">说明</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.kind}>
                    <td className="td">{r.name}</td>
                    <td className="td">
                      <Badge color={STATUS_COLOR[r.status]}>
                        {{ created: "已生成", skipped: "已跳过", failed: "失败", disabled: "已停用" }[r.status]}
                      </Badge>
                    </td>
                    <td className="td-num">{r.amount ? fmtMoney(r.amount) : ""}</td>
                    <td className="td">{r.voucher_no || ""}</td>
                    <td className="td text-xs text-slate-500">{r.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-end">
              <button className="btn-primary" onClick={finish}>完成</button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

/* ---------- 结转配置 ---------- */

const ACCOUNT_ROLES = {
  expense: "费用科目", credit: "对方科目", payable: "应付科目", bank: "银行科目",
  tax: "代扣个税科目", income: "收入科目", vat: "增值税科目", gain_loss: "汇兑损益科目",
  profit: "本年利润科目", retained: "未分配利润科目",
  city_expense: "城建税费用", city_payable: "应交城建税",
  edu_expense: "教育费附加费用", edu_payable: "应交教育费附加",
  local_edu_expense: "地方教育附加费用", local_edu_payable: "应交地方教育附加",
};

const RATE_LABELS = {
  city: "城建税率", edu: "教育费附加率", local_edu: "地方教育附加率",
  income_tax: "所得税税率", water_fund: "地方水利基金率", union_fee: "工会经费率",
  stamp_tax: "印花税率",
};

function ConfigDialog({ onClose, onSaved, onError }) {
  const [cfg, setCfg] = useState(null);
  const [names, setNames] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiGet("/api/carryover/config").then(setCfg).catch((e) => setError(e.message));
    apiGet("/api/carryover/kinds")
      .then((rows) => setNames(Object.fromEntries(rows.map((r) => [r.kind, r.name]))))
      .catch(() => {});
  }, []);

  const setStep = (kind, patch) =>
    setCfg({ ...cfg, steps: { ...cfg.steps, [kind]: { ...cfg.steps[kind], ...patch } } });

  const setAccount = (kind, role, code) =>
    setStep(kind, { accounts: { ...cfg.steps[kind].accounts, [role]: code } });

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await apiPut("/api/carryover/config", cfg);
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open wide title="结转配置" onClose={onClose}>
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {!cfg && !error && <div className="text-sm text-slate-400">加载中…</div>}
        {cfg && (
          <>
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="th">启用</th>
                    <th className="th">步骤</th>
                    <th className="th w-20">顺序</th>
                    <th className="th w-32">金额来源</th>
                    <th className="th w-32">默认金额</th>
                    <th className="th">科目设置</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(cfg.steps)
                    .sort((a, b) => a[1].order - b[1].order)
                    .map(([kind, sc]) => (
                      <tr key={kind}>
                        <td className="td text-center">
                          <input
                            type="checkbox"
                            checked={sc.enabled}
                            onChange={(e) => setStep(kind, { enabled: e.target.checked })}
                          />
                        </td>
                        <td className="td whitespace-nowrap">{names[kind] || kind}</td>
                        <td className="td p-1">
                          <input
                            type="number"
                            className="input text-right"
                            value={sc.order}
                            onChange={(e) => setStep(kind, { order: Number(e.target.value) })}
                          />
                        </td>
                        <td className="td p-1">
                          <select
                            className="input"
                            value={sc.amount_mode}
                            onChange={(e) => setStep(kind, { amount_mode: e.target.value })}
                          >
                            <option value="manual">手工录入</option>
                            <option value="auto">自动计算</option>
                            <option value="last">按上期金额</option>
                          </select>
                        </td>
                        <td className="td p-1">
                          <input
                            className="input text-right tabular-nums"
                            value={sc.default_amount ?? 0}
                            onChange={(e) =>
                              setStep(kind, { default_amount: e.target.value.replace(/[^\d.]/g, "") })
                            }
                          />
                        </td>
                        <td className="td">
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(sc.accounts).map(([role, code]) => (
                              <label key={role} className="flex items-center gap-1 text-xs text-slate-500">
                                {ACCOUNT_ROLES[role] || role}
                                <input
                                  className="input input-sm w-20 py-1 text-xs"
                                  value={code}
                                  onChange={(e) => setAccount(kind, role, e.target.value)}
                                />
                              </label>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            <div>
              <h3 className="font-semibold text-slate-800 mb-2">税率 / 费率</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Object.entries(cfg.rates).map(([k, v]) => (
                  <label key={k} className="text-xs text-slate-500">
                    {RATE_LABELS[k] || k}
                    <input
                      className="input mt-1"
                      value={v}
                      onChange={(e) =>
                        setCfg({ ...cfg, rates: { ...cfg.rates, [k]: e.target.value.replace(/[^\d.]/g, "") } })
                      }
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={onClose}>取消</button>
              <button className="btn-primary" onClick={save} disabled={busy}>
                {busy ? "保存中…" : "保存配置"}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
