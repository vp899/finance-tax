"use client";

import { useCallback, useEffect, useState } from "react";
import { apiDel, apiGet, apiPost, apiPut, fmtMoney } from "@/lib/api";
import AccountManager from "@/components/AccountManager";
import { Alert, Badge, Empty, Modal, Tabs, Amt } from "@/components/ui";

const TABS = [
  { key: "basic", label: "基本设置" },
  { key: "accounts", label: "会计科目" },
  { key: "opening", label: "科目期初" },
  { key: "types", label: "凭证类型" },
  { key: "units", label: "计量单位" },
  { key: "currency", label: "币种设置" },
  { key: "cashflow", label: "现金流量对照" },
  { key: "assets", label: "固定资产/无形资产" },
];

export default function SettingsPage() {
  const [tab, setTab] = useState("basic");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">财税设置</h1>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "basic" && <BasicSettings />}
      {tab === "accounts" && <AccountManager />}
      {tab === "opening" && <Opening />}
      {tab === "types" && <VoucherTypes />}
      {tab === "units" && <Units />}
      {tab === "currency" && <Currencies />}
      {tab === "cashflow" && <CashflowMap />}
      {tab === "assets" && <Assets />}
    </div>
  );
}

function useMsg() {
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  return {
    error, ok, setError, setOk,
    node: (
      <>
        {error && <Alert onClose={() => setError("")}>{error}</Alert>}
        {ok && <Alert type="success" onClose={() => setOk("")}>{ok}</Alert>}
      </>
    ),
  };
}

function BasicSettings() {
  const [s, setS] = useState(null);
  const msg = useMsg();
  useEffect(() => {
    apiGet("/api/settings").then(setS).catch((e) => msg.setError(e.message));
  }, []);
  if (!s) return <div className="card p-6 text-slate-400">加载中…</div>;

  const fields = [
    ["company_name", "企业名称"],
    ["tax_no", "纳税人识别号"],
    ["vat_rate", "增值税征收率（如 0.03）"],
    ["city_tax_rate", "城建税税率（如 0.07）"],
    ["edu_rate", "教育费附加费率（如 0.03）"],
    ["local_edu_rate", "地方教育附加费率（如 0.02）"],
    ["income_tax_rate", "企业所得税税率（如 0.25）"],
    ["vat_free_month_limit", "小规模月销售额免征额"],
    ["vat_free_quarter_limit", "小规模季销售额免征额"],
  ];

  const staff = [
    ["staff_bookkeeper", "记账人"],
    ["staff_reviewer", "审核人"],
    ["staff_cashier", "出纳人"],
    ["staff_supervisor", "会计主管"],
  ];

  const decimals = [
    ["decimal_qty", "数量小数位（最多 2 位，不足补零）"],
    ["decimal_price", "单价小数位（最多 2 位，不足补零）"],
    ["decimal_rate", "汇率小数位（最多 6 位）"],
  ];

  const auxSwitches = [
    ["aux_switch_project", "项目"], ["aux_switch_customer", "客户"],
    ["aux_switch_supplier", "供应商"], ["aux_switch_dept", "部门"],
    ["aux_switch_employee", "员工"], ["aux_switch_inventory", "存货"],
  ];

  return (
    <div className="card p-6 space-y-4">
      {msg.node}
      <div className="grid md:grid-cols-3 gap-4">
        <div>
          <label className="label">纳税人类型</label>
          <select
            className="input"
            value={s.taxpayer_type || "small"}
            onChange={(e) => setS({ ...s, taxpayer_type: e.target.value })}
          >
            <option value="small">小规模纳税人</option>
            <option value="general">一般纳税人</option>
          </select>
        </div>
        <div>
          <label className="label">会计准则</label>
          <select
            className="input"
            value={s.accounting_standard || "xqy2013"}
            onChange={(e) => setS({ ...s, accounting_standard: e.target.value })}
          >
            <option value="xqy2013">2013 小企业会计准则</option>
          </select>
        </div>
      </div>
      <div className="grid md:grid-cols-3 gap-4">
        {fields.map(([k, label]) => (
          <div key={k}>
            <label className="label">{label}</label>
            <input className="input" value={s[k] || ""} onChange={(e) => setS({ ...s, [k]: e.target.value })} />
          </div>
        ))}
      </div>

      <div className="border-t border-slate-100 pt-4">
        <h3 className="font-semibold text-slate-800 mb-2">财务人员</h3>
        <div className="grid md:grid-cols-4 gap-4">
          {staff.map(([k, label]) => (
            <div key={k}>
              <label className="label">{label}</label>
              <input className="input" value={s[k] || ""} onChange={(e) => setS({ ...s, [k]: e.target.value })} />
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-slate-100 pt-4">
        <h3 className="font-semibold text-slate-800 mb-2">小数位设置</h3>
        <div className="grid md:grid-cols-3 gap-4">
          {decimals.map(([k, label]) => (
            <div key={k}>
              <label className="label">{label}</label>
              <input type="number" min="0" max="8" className="input"
                     value={s[k] ?? ""}
                     onChange={(e) => setS({ ...s, [k]: e.target.value.replace(/[^\d]/g, "") })} />
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-slate-100 pt-4">
        <h3 className="font-semibold text-slate-800 mb-2">辅助核算开关</h3>
        <div className="flex flex-wrap items-center gap-5">
          {auxSwitches.map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={s[k] !== "0"}
                     onChange={(e) => setS({ ...s, [k]: e.target.checked ? "1" : "0" })} />
              {label}
            </label>
          ))}
        </div>
        <div className="text-xs text-slate-400 mt-2">停用后，科目编辑中的对应辅助核算项不可勾选。</div>
      </div>
      <div className="flex justify-end">
        <button
          className="btn-primary"
          onClick={async () => {
            try {
              await apiPut("/api/settings", s);
              msg.setOk("设置已保存");
            } catch (e) {
              msg.setError(e.message);
            }
          }}
        >
          保存设置
        </button>
      </div>
    </div>
  );
}

function Opening() {
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [yearList, setYearList] = useState([]);
  const [yearCfg, setYearCfg] = useState("");
  const [data, setData] = useState(null);
  const [edits, setEdits] = useState({});
  const msg = useMsg();
  const load = useCallback(() => {
    apiGet(`/api/accounts/openings/list?year=${year}`)
      .then((d) => {
        setData(d);
        setEdits({});
        setYearList(Array.from(new Set([...(d.years || []), d.year, String(new Date().getFullYear())])).sort());
        if (d.opening_year) setYearCfg((c) => c || d.opening_year);
      })
      .catch((e) => msg.setError(e.message));
  }, [year]);
  useEffect(load, [load]);

  const saveYearCfg = async () => {
    try {
      await apiPost("/api/accounts/openings/set-year", { year: yearCfg });
      msg.setOk(`期初年份已设置为 ${yearCfg}`);
      load();
    } catch (e) {
      msg.setError(e.message);
    }
  };

  const totalD = (data?.rows || []).reduce(
    (s, r) => s + (Number(edits[r.account_id] !== undefined ? (edits[r.account_id].debit ?? "") : r.debit) || 0), 0);
  const totalC = (data?.rows || []).reduce(
    (s, r) => s + (Number(edits[r.account_id] !== undefined ? (edits[r.account_id].credit ?? "") : r.credit) || 0), 0);
  const balanced = Math.abs(totalD - totalC) < 0.005;

  return (
    <div className="card">
      <div className="flex flex-wrap items-center gap-3 p-4 border-b border-slate-200">
        <select className="input w-28" value={year} onChange={(e) => setYear(e.target.value)}>
          {yearList.map((y) => <option key={y} value={y}>{y} 年度</option>)}
          {!yearList.includes(year) && <option value={year}>{year} 年度</option>}
        </select>
        <input className="input w-24" value={year} onChange={(e) => setYear(e.target.value.replace(/[^\d]/g, "").slice(0, 4))} />
        <span className="text-sm text-slate-500">年度期初余额（借方合计 <Amt v={totalD} /> / 贷方合计 <Amt v={totalC} />）</span>
        {balanced ? <Badge color="green">试算平衡</Badge> : <Badge color="red">不平衡</Badge>}
        {data?.anchor_year && data.anchor_year !== data.year && (
          <span className="text-xs text-brand-700 bg-brand-50 border border-brand-200 rounded px-2 py-1">
            年期初未录入，已按 {data.anchor_year} 年度连续累计自动更新（保存后写入本年度）
          </span>
        )}
        <span className="text-xs text-slate-400">可直接修改已有期初；保存时按全年合并口径校验试算平衡</span>
        <div className="flex-1" />
        <button
          className="btn-primary"
          disabled={!balanced}
          onClick={async () => {
            // 写入本次修改的行 + 非零的年期初（含自动连续累计的年期初），避免只改一行导致其它科目被清零
            const rows = (data?.rows || [])
              .map((r) => {
                const e = edits[r.account_id] || {};
                return {
                  account_id: r.account_id,
                  debit: Number(e.debit !== undefined ? e.debit : r.debit) || 0,
                  credit: Number(e.credit !== undefined ? e.credit : r.credit) || 0,
                  quantity: r.quantity || 0,
                };
              })
              .filter((row) => row.debit || row.credit || edits[row.account_id] !== undefined);
            try {
              await apiPut("/api/accounts/openings/save", { year, rows });
              msg.setOk("期初余额已保存");
              load();
            } catch (e) {
              msg.setError(e.message);
            }
          }}
        >
          保存期初
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-slate-200 bg-slate-50/60">
        <span className="text-sm text-slate-600 font-medium">科目期初年份设置</span>
        <input className="input w-24" placeholder="YYYY"
               value={yearCfg}
               onChange={(e) => setYearCfg(e.target.value.replace(/[^\d]/g, "").slice(0, 4))} />
        <button className="btn-ghost" onClick={saveYearCfg}>保存年份</button>
        <span className="text-xs text-slate-400">
          建账年份：科目期初默认在此年份下录入；新年度未录期初时自动锚定最近有期初的年度连续累计。
          年度切换后可为不同年度分别录入期初。
        </span>
      </div>
      {msg.node && <div className="p-4">{msg.node}</div>}
      <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">科目</th>
              <th className="th text-right">期初借方</th>
              <th className="th text-right">期初贷方</th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows || []).map((r) => {
              const e = edits[r.account_id] || {};
              return (
                <tr key={r.account_id} className="hover:bg-slate-50">
                  <td className="td">
                    {r.code} {r.name}
                    {r.is_leaf === false && <Badge color="amber">非末级</Badge>}
                    {r.carried && <Badge color="blue">自动年期初</Badge>}
                  </td>
                  <td className="td p-1">
                    <input
                      className="input text-right tabular-nums"
                      value={e.debit !== undefined ? e.debit : r.debit || ""}
                      onChange={(ev) => setEdits({ ...edits, [r.account_id]: { ...e, debit: ev.target.value.replace(/[^\d.]/g, "") } })}
                    />
                  </td>
                  <td className="td p-1">
                    <input
                      className="input text-right tabular-nums"
                      value={e.credit !== undefined ? e.credit : r.credit || ""}
                      onChange={(ev) => setEdits({ ...edits, [r.account_id]: { ...e, credit: ev.target.value.replace(/[^\d.]/g, "") } })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VoucherTypes() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: "", prefix: "" });
  const msg = useMsg();
  const load = () => apiGet("/api/settings/voucher-types").then(setRows).catch((e) => msg.setError(e.message));
  useEffect(() => { load(); }, []);
  return (
    <div className="card p-5 space-y-4">
      {msg.node}
      <div className="flex gap-3">
        <input className="input w-48" placeholder="名称，如 收款凭证" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="input w-32" placeholder="前缀，如 收" value={form.prefix} onChange={(e) => setForm({ ...form, prefix: e.target.value })} />
        <button
          className="btn-primary"
          onClick={async () => {
            try {
              await apiPost("/api/settings/voucher-types", form);
              setForm({ name: "", prefix: "" });
              load();
            } catch (e) {
              msg.setError(e.message);
            }
          }}
        >
          添加
        </button>
      </div>
      <table className="w-full">
        <thead>
          <tr>
            <th className="th">名称</th>
            <th className="th">前缀</th>
            <th className="th">默认</th>
            <th className="th text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id}>
              <td className="td">{t.name}</td>
              <td className="td">{t.prefix}</td>
              <td className="td">{t.is_default ? <Badge color="blue">默认</Badge> : ""}</td>
              <td className="td text-right">
                <button
                  className="text-rose-600 text-xs hover:underline"
                  onClick={async () => {
                    await apiDel(`/api/settings/voucher-types/${t.id}`);
                    load();
                  }}
                >
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Units() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: "", symbol: "" });
  const msg = useMsg();
  const load = () => apiGet("/api/settings/units").then(setRows).catch((e) => msg.setError(e.message));
  useEffect(() => { load(); }, []);
  return (
    <div className="card p-5 space-y-4">
      {msg.node}
      <div className="flex gap-3">
        <input className="input w-40" placeholder="单位名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="input w-32" placeholder="符号" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} />
        <button
          className="btn-primary"
          onClick={async () => {
            try {
              await apiPost("/api/settings/units", form);
              setForm({ name: "", symbol: "" });
              load();
            } catch (e) {
              msg.setError(e.message);
            }
          }}
        >
          添加
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {rows.map((u) => (
          <div key={u.id} className="flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-1.5 text-sm">
            {u.name}（{u.symbol || "—"}）
            <button
              className="text-rose-500"
              onClick={async () => {
                await apiDel(`/api/settings/units/${u.id}`);
                load();
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Currencies() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ code: "", name: "", rate: "1" });
  const msg = useMsg();
  const load = () => apiGet("/api/settings/currencies").then(setRows).catch((e) => msg.setError(e.message));
  useEffect(() => { load(); }, []);
  return (
    <div className="card p-5 space-y-4">
      {msg.node}
      <div className="flex gap-3">
        <input className="input w-28" placeholder="代码 USD" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        <input className="input w-32" placeholder="名称 美元" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="input w-32" placeholder="汇率" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} />
        <button
          className="btn-primary"
          onClick={async () => {
            try {
              await apiPost("/api/settings/currencies", form);
              setForm({ code: "", name: "", rate: "1" });
              load();
            } catch (e) {
              msg.setError(e.message);
            }
          }}
        >
          添加
        </button>
      </div>
      <table className="w-full">
        <thead>
          <tr>
            <th className="th">代码</th>
            <th className="th">名称</th>
            <th className="th text-right">汇率</th>
            <th className="th">默认</th>
            <th className="th text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td className="td">{c.code}</td>
              <td className="td">{c.name}</td>
              <td className="td p-1">
                <input
                  className="input text-right tabular-nums"
                  defaultValue={c.rate}
                  onBlur={async (e) => {
                    await apiPut(`/api/settings/currencies/${c.id}`, { rate: Number(e.target.value) || 1 });
                    load();
                  }}
                />
              </td>
              <td className="td">{c.is_default ? <Badge color="blue">默认</Badge> : ""}</td>
              <td className="td text-right">
                <button
                  className="text-rose-600 text-xs hover:underline"
                  onClick={async () => {
                    await apiDel(`/api/settings/currencies/${c.id}`);
                    load();
                  }}
                >
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CF_MAP_TABS = [
  { key: "all", label: "全部" },
  { key: "asset", label: "资产" },
  { key: "liability", label: "负债" },
  { key: "equity", label: "权益" },
  { key: "cost", label: "成本" },
  { key: "pl", label: "损益" },
];

function cfCatMatch(tab, category) {
  if (tab === "all") return true;
  if (tab === "pl") return category === "income" || category === "expense";
  return category === tab;
}

function CashflowMap() {
  const [rows, setRows] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState("all");
  const [form, setForm] = useState({ account_id: "", cashflow_code: "" });
  const msg = useMsg();
  const load = () => {
    apiGet("/api/settings/cashflow-map").then(setRows).catch(() => {});
    apiGet("/api/accounts").then(setAccounts).catch(() => {});
    apiGet("/api/settings/cashflow-items").then(setItems).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const shown = rows.filter((r) => cfCatMatch(tab, r.category));
  const catAccounts = accounts.filter((a) => cfCatMatch(tab, a.category));
  const tabs = CF_MAP_TABS.map((t) => ({
    ...t,
    label: t.key === "all"
      ? `全部 ${rows.length}`
      : `${t.label} ${rows.filter((r) => cfCatMatch(t.key, r.category)).length}`,
  }));
  return (
    <div className="card">
      <div className="p-4 border-b border-slate-200 space-y-3">
        <Tabs tabs={tabs} active={tab} onChange={setTab} />
        <div className="flex flex-wrap gap-3 items-center">
          <select className="input w-72" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}>
            <option value="">选择科目…</option>
            {catAccounts.map((a) => (
              <option key={a.id} value={a.id}>{a.code} {a.name}</option>
            ))}
          </select>
          <select className="input w-96" value={form.cashflow_code} onChange={(e) => setForm({ ...form, cashflow_code: e.target.value })}>
            <option value="">选择现金流量项目…</option>
            {items.map((c) => (
              <option key={c.code} value={c.code}>{c.code} {c.name}</option>
            ))}
          </select>
          <button
            className="btn-primary"
            onClick={async () => {
              try {
                await apiPost("/api/settings/cashflow-map", {
                  account_id: Number(form.account_id),
                  cashflow_code: form.cashflow_code,
                });
                load();
              } catch (e) {
                msg.setError(e.message);
              }
            }}
          >
            保存对照
          </button>
        </div>
      </div>
      {msg.node && <div className="p-4">{msg.node}</div>}
      <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">对方科目</th>
              <th className="th">核算类型</th>
              <th className="th">现金流量项目</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <td className="td">
                  <span className="font-mono text-xs text-slate-400 mr-2">{r.account_code}</span>
                  {r.account_name}
                </td>
                <td className="td text-xs text-slate-500">{r.category_name || ""}</td>
                <td className="td">
                  {r.cashflow_code} {items.find((i) => i.code === r.cashflow_code)?.name || ""}
                </td>
                <td className="td text-right">
                  <button
                    className="text-rose-600 text-xs hover:underline"
                    onClick={async () => {
                      await apiDel(`/api/settings/cashflow-map/${r.id}`);
                      load();
                    }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && (
          <div className="p-6 text-center text-sm text-slate-400">当前类别暂无对照记录</div>
        )}
      </div>
    </div>
  );
}

function Assets() {
  const [fixed, setFixed] = useState([]);
  const [intangible, setIntangible] = useState([]);
  const [form, setForm] = useState({ name: "", original_value: "", residual_rate: "0.05", life_months: "120", amort_months: "120" });
  const msg = useMsg();
  const load = () => {
    apiGet("/api/carryover/assets/fixed").then(setFixed).catch(() => {});
    apiGet("/api/carryover/assets/intangible").then(setIntangible).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-4">
      {msg.node}
      <div className="card">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
          <h3 className="font-semibold">固定资产（计提折旧）</h3>
          <button
            className="btn-primary btn-sm"
            onClick={async () => {
              const name = prompt("资产名称");
              if (!name) return;
              const original_value = Number(prompt("原值（元）") || 0);
              const life_months = Number(prompt("使用寿命（月）") || 120);
              const residual_rate = Number(prompt("残值率（如 0.05）", "0.05") || 0);
              await apiPost("/api/carryover/assets/fixed", { name, original_value, life_months, residual_rate });
              load();
            }}
          >
            ＋ 添加
          </button>
        </div>
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">名称</th>
              <th className="th text-right">原值</th>
              <th className="th text-right">残值率</th>
              <th className="th text-right">寿命(月)</th>
              <th className="th text-right">月折旧</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {fixed.map((f) => (
              <tr key={f.id}>
                <td className="td">{f.name}</td>
                <td className="td-num"><Amt v={f.original_value} /></td>
                <td className="td-num">{(f.residual_rate * 100).toFixed(0)}%</td>
                <td className="td-num">{f.life_months}</td>
                <td className="td-num font-medium"><Amt v={f.monthly_depreciation} /></td>
                <td className="td text-right">
                  <button
                    className="text-rose-600 text-xs hover:underline"
                    onClick={async () => {
                      if (!confirm(`删除固定资产 ${f.name}？`)) return;
                      await apiDel(`/api/carryover/assets/fixed/${f.id}`);
                      load();
                    }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!fixed.length && <Empty text="暂无固定资产" />}
      </div>

      <div className="card">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
          <h3 className="font-semibold">无形资产（摊销）</h3>
          <button
            className="btn-primary btn-sm"
            onClick={async () => {
              const name = prompt("资产名称");
              if (!name) return;
              const original_value = Number(prompt("原值（元）") || 0);
              const amort_months = Number(prompt("摊销期限（月）") || 120);
              await apiPost("/api/carryover/assets/intangible", { name, original_value, amort_months });
              load();
            }}
          >
            ＋ 添加
          </button>
        </div>
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">名称</th>
              <th className="th text-right">原值</th>
              <th className="th text-right">摊销期(月)</th>
              <th className="th text-right">月摊销</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {intangible.map((f) => (
              <tr key={f.id}>
                <td className="td">{f.name}</td>
                <td className="td-num"><Amt v={f.original_value} /></td>
                <td className="td-num">{f.amort_months}</td>
                <td className="td-num font-medium"><Amt v={f.monthly_amortization} /></td>
                <td className="td text-right">
                  <button
                    className="text-rose-600 text-xs hover:underline"
                    onClick={async () => {
                      if (!confirm(`删除无形资产 ${f.name}？`)) return;
                      await apiDel(`/api/carryover/assets/intangible/${f.id}`);
                      load();
                    }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!intangible.length && <Empty text="暂无无形资产" />}
      </div>
    </div>
  );
}
