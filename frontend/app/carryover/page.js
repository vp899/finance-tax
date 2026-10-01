"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, curPeriod, fmtMoney } from "@/lib/api";
import { Alert, Badge, Empty, Modal } from "@/components/ui";

const OPS = [
  { kind: "sales_cost", name: "结转销售成本", icon: "📦", desc: "借：主营业务成本　贷：库存商品", manual: true },
  { kind: "salary", name: "计提工资", icon: "💼", desc: "借：管理费用-工资　贷：应付职工薪酬", manual: true },
  { kind: "depreciation", name: "计提折旧", icon: "🏭", desc: "借：管理费用-折旧费　贷：累计折旧", auto: true },
  { kind: "amortization", name: "摊销无形资产", icon: "💡", desc: "借：管理费用-摊销费　贷：累计摊销", auto: true },
  { kind: "profit", name: "结转本期损益", icon: "⚖️", desc: "损益类科目余额转入本年利润", auto: true },
  { kind: "tax", name: "计提税金", icon: "🧾", desc: "城建税 / 教育费附加 / 地方教育附加", auto: true },
  { kind: "income_tax", name: "计提所得税", icon: "🏛️", desc: "借：所得税费用　贷：应交所得税", auto: true },
  { kind: "vat_free", name: "免交增值税", icon: "🎯", desc: "小规模未达起征点转入营业外收入", auto: true },
];

export default function CarryoverPage() {
  const [period, setPeriod] = useState(curPeriod());
  const [op, setOp] = useState(null);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [records, setRecords] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [reload, setReload] = useState(0);

  const load = useCallback(() => {
    apiGet(`/api/carryover/records?period=${period}`).then(setRecords).catch(() => {});
    apiGet("/api/carryover/periods").then(setPeriods).catch(() => {});
  }, [period]);
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
    if (!confirm(`确认反结转【${rec.kind}】凭证 ${rec.voucher_no}？该凭证将被作废。`)) return;
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">结转与结账</h1>
        <div className="flex items-center gap-3">
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
        </div>
      </div>

      {error && <Alert onClose={() => setError("")}>{error}</Alert>}
      {ok && <Alert type="success" onClose={() => setOk("")}>{ok}</Alert>}

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {OPS.map((o) => (
          <button
            key={o.kind}
            onClick={() => {
              setError("");
              setOp(o);
            }}
            className="card p-4 text-left hover:shadow-md hover:border-brand-300 transition-all"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">{o.icon}</span>
              <span className="text-xs text-slate-400">
                {o.auto ? "自动计算" : "录入金额"}
              </span>
            </div>
            <div className="mt-2 font-semibold text-slate-800">{o.name}</div>
            <div className="text-xs text-slate-500 mt-1 leading-relaxed">{o.desc}</div>
          </button>
        ))}
      </div>

      <div className="card">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200">
          <h2 className="font-semibold text-slate-800">{period} 结转记录</h2>
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
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
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
                  <td className="td">{OPS.find((o) => o.kind === r.kind)?.name || r.kind}</td>
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
          {!records.length && <Empty text="该期间暂无结转记录" />}
        </div>
        <div className="px-5 py-3 text-xs text-slate-400 border-t border-slate-100 leading-relaxed">
          结账检查：试算平衡 → 无草稿凭证 → 本期损益已结平。如需跳过损益检查请使用【强制结账】。
          反结转会作废对应结转凭证，报表金额自动回退。
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
    </div>
  );
}

function OpDialog({ op, period, onClose, onDone, onError }) {
  const [preview, setPreview] = useState(null);
  const [amount, setAmount] = useState("");
  const [extra, setExtra] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPreview(null);
    setError("");
    apiGet(`/api/carryover/preview/${op.kind}?period=${period}`)
      .then((p) => {
        setPreview(p);
        if (op.kind === "sales_cost") setAmount(String(p.suggested_amount || ""));
        if (op.kind === "salary") setAmount(String(p.suggested_amount || ""));
        if (op.kind === "income_tax") setAmount(String(p.amount ?? ""));
        if (op.kind === "vat_free") setAmount(String(p.vat_amount ?? ""));
        if (op.kind === "tax") setExtra({ vat_base: String(p.vat_base ?? "") });
      })
      .catch((e) => setError(e.message));
  }, [op.kind, period]);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const body = { period };
      if (op.manual) body.amount = Number(amount) || 0;
      if (op.kind === "income_tax" && amount !== "") body.amount = Number(amount) || 0;
      if (op.kind === "vat_free" && amount !== "") body.amount = Number(amount) || 0;
      if (op.kind === "tax" && extra.vat_base !== "") body.vat_base = Number(extra.vat_base) || 0;
      const r = await apiPost(`/api/carryover/${op.kind}`, body);
      onDone(`${op.name}完成，生成凭证 ${r.voucher_no}，金额 ${fmtMoney(r.amount)}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={`${op.name} — ${period}`} onClose={onClose}>
      <div className="space-y-4">
        <div className="text-sm text-slate-500 bg-slate-50 rounded-lg px-4 py-2.5">{op.desc}</div>

        {error && <Alert>{error}</Alert>}

        {preview && op.kind === "sales_cost" && (
          <div className="text-sm space-y-1">
            <div>本期营业收入：<b>{fmtMoney(preview.period_income)}</b></div>
            <div>上期结转成本参考：{fmtMoney(preview.suggested_amount)}</div>
            <label className="label mt-2">本次结转金额</label>
            <input className="input" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </div>
        )}

        {preview && op.kind === "salary" && (
          <div className="text-sm space-y-1">
            <div>上期计提参考：{fmtMoney(preview.suggested_amount)}</div>
            <label className="label mt-2">本次计提金额</label>
            <input className="input" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </div>
        )}

        {preview && op.kind === "depreciation" && (
          <div className="text-sm space-y-2">
            {preview.items.map((it) => (
              <div key={it.id} className="flex justify-between border-b border-dashed py-1">
                <span>{it.name}</span>
                <span className="tabular-nums">{fmtMoney(it.amount)}</span>
              </div>
            ))}
            <div className="flex justify-between font-semibold">
              <span>本月折旧合计</span>
              <span>{fmtMoney(preview.total)}</span>
            </div>
          </div>
        )}

        {preview && op.kind === "amortization" && (
          <div className="text-sm space-y-2">
            {preview.items.map((it) => (
              <div key={it.id} className="flex justify-between border-b border-dashed py-1">
                <span>{it.name}</span>
                <span className="tabular-nums">{fmtMoney(it.amount)}</span>
              </div>
            ))}
            <div className="flex justify-between font-semibold">
              <span>本月摊销合计</span>
              <span>{fmtMoney(preview.total)}</span>
            </div>
          </div>
        )}

        {preview && op.kind === "profit" && (
          <div className="text-sm">
            <div className="max-h-64 overflow-auto border border-slate-200 rounded-lg">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="th">科目</th>
                    <th className="th">方向</th>
                    <th className="th text-right">金额</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.lines.map((l) => (
                    <tr key={l.account_code}>
                      <td className="td">{l.account_code} {l.account_name}</td>
                      <td className="td text-xs">
                        {l.direction === "income" ? "结转收入" : "结转费用"}
                      </td>
                      <td className="td-num">{fmtMoney(l.amount)}</td>
                    </tr>
                  ))}
                  <tr className="bg-slate-50 font-semibold">
                    <td className="td" colSpan={2}>本期净利润</td>
                    <td className="td-num">{fmtMoney(preview.net_profit)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {preview && op.kind === "tax" && (
          <div className="text-sm space-y-2">
            <label className="label">计税基数（本期应交增值税）</label>
            <input
              className="input"
              value={extra.vat_base ?? ""}
              onChange={(e) => setExtra({ vat_base: e.target.value })}
            />
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

        {preview && op.kind === "income_tax" && (
          <div className="text-sm space-y-1">
            <div>本年累计利润总额：<b>{fmtMoney(preview.total_profit_ytd)}</b></div>
            <div>适用税率：{(preview.rate * 100).toFixed(2)}%</div>
            <div>本年已计提所得税：{fmtMoney(preview.accrued_ytd)}</div>
            <label className="label mt-2">本次计提金额（可修改）</label>
            <input className="input" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
        )}

        {preview && op.kind === "vat_free" && (
          <div className="text-sm space-y-1">
            <div>本月销售额：<b>{fmtMoney(preview.sales_month)}</b>（月限额 {fmtMoney(preview.month_limit)}）</div>
            <div>本季销售额：<b>{fmtMoney(preview.sales_quarter)}</b>（季限额 {fmtMoney(preview.quarter_limit)}）</div>
            <div>
              免征资格：
              {preview.eligible ? (
                <span className="text-emerald-600">符合免征条件 ✓</span>
              ) : (
                <span className="text-rose-600">不符合免征条件（或非小规模纳税人）</span>
              )}
            </div>
            <label className="label mt-2">免交增值税金额（可修改）</label>
            <input className="input" value={amount} onChange={(e) => setAmount(e.target.value)} />
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
