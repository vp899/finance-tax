"use client";

import { useCallback, useEffect, useState } from "react";
import { apiDel, apiGet, apiPost, apiPut, fmtMoney } from "@/lib/api";
import { Alert, Badge, Empty, Modal, Tabs } from "@/components/ui";

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
      {tab === "accounts" && <Accounts />}
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

function Accounts() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", parent_code: "", direction: "D", category: "asset", pinyin: "" });
  const msg = useMsg();
  const load = useCallback(() => {
    apiGet("/api/accounts").then(setRows).catch((e) => msg.setError(e.message));
  }, []);
  useEffect(load, [load]);

  const filtered = rows.filter(
    (a) => !q || a.code.includes(q) || a.name.includes(q) || a.pinyin.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="card">
      <div className="flex items-center gap-3 p-4 border-b border-slate-200">
        <input className="input w-64" placeholder="搜索科目编码/名称/拼音" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex-1" />
        <button className="btn-primary" onClick={() => setAdding(true)}>＋ 新增科目</button>
      </div>
      {msg.node && <div className="p-4">{msg.node}</div>}
      <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">编码</th>
              <th className="th">名称</th>
              <th className="th">方向</th>
              <th className="th">类别</th>
              <th className="th">末级</th>
              <th className="th">拼音</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a) => (
              <tr key={a.id} className="hover:bg-slate-50">
                <td className="td font-mono text-xs">{a.code}</td>
                <td className="td">
                  <span style={{ paddingLeft: (a.level - 1) * 16 }}>{a.name}</span>
                </td>
                <td className="td text-xs">{a.direction === "D" ? "借" : "贷"}</td>
                <td className="td text-xs text-slate-500">
                  {{ asset: "资产", liability: "负债", equity: "权益", income: "收入", expense: "成本费用" }[a.category]}
                </td>
                <td className="td">{a.is_leaf ? <Badge color="green">末级</Badge> : <Badge>上级</Badge>}</td>
                <td className="td text-xs text-slate-400">{a.pinyin}</td>
                <td className="td text-right">
                  {!["asset", "liability", "equity", "income", "expense"].includes(a.category) || true ? (
                    <button
                      className="text-rose-600 text-xs hover:underline"
                      onClick={async () => {
                        if (!confirm(`确认删除科目 ${a.code} ${a.name}？`)) return;
                        try {
                          await apiDel(`/api/accounts/${a.id}`);
                          load();
                        } catch (e) {
                          msg.setError(e.message);
                        }
                      }}
                    >
                      删除
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={adding} title="新增会计科目" onClose={() => setAdding(false)}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">科目编码</label>
            <input className="input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          </div>
          <div>
            <label className="label">科目名称</label>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="label">上级科目编码（可空）</label>
            <input className="input" value={form.parent_code} onChange={(e) => setForm({ ...form, parent_code: e.target.value })} />
          </div>
          <div>
            <label className="label">余额方向</label>
            <select className="input" value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
              <option value="D">借方</option>
              <option value="C">贷方</option>
            </select>
          </div>
          <div>
            <label className="label">类别</label>
            <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="asset">资产</option>
              <option value="liability">负债</option>
              <option value="equity">权益</option>
              <option value="income">收入</option>
              <option value="expense">成本费用</option>
            </select>
          </div>
          <div>
            <label className="label">拼音（用于智能补全）</label>
            <input className="input" value={form.pinyin} onChange={(e) => setForm({ ...form, pinyin: e.target.value })} />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button className="btn-ghost" onClick={() => setAdding(false)}>取消</button>
          <button
            className="btn-primary"
            onClick={async () => {
              try {
                await apiPost("/api/accounts", form);
                setAdding(false);
                setForm({ code: "", name: "", parent_code: "", direction: "D", category: "asset", pinyin: "" });
                load();
                msg.setOk("科目已新增");
              } catch (e) {
                msg.setError(e.message);
              }
            }}
          >
            保存
          </button>
        </div>
      </Modal>
    </div>
  );
}

function Opening() {
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [data, setData] = useState(null);
  const [edits, setEdits] = useState({});
  const msg = useMsg();
  const load = useCallback(() => {
    apiGet(`/api/accounts/openings/list?year=${year}`)
      .then((d) => {
        setData(d);
        setEdits({});
      })
      .catch((e) => msg.setError(e.message));
  }, [year]);
  useEffect(load, [load]);

  const totalD = (data?.rows || []).reduce(
    (s, r) => s + (Number(edits[r.account_id] !== undefined ? (edits[r.account_id].debit ?? "") : r.debit) || 0), 0);
  const totalC = (data?.rows || []).reduce(
    (s, r) => s + (Number(edits[r.account_id] !== undefined ? (edits[r.account_id].credit ?? "") : r.credit) || 0), 0);
  const balanced = Math.abs(totalD - totalC) < 0.005;

  return (
    <div className="card">
      <div className="flex items-center gap-3 p-4 border-b border-slate-200">
        <input className="input w-32" value={year} onChange={(e) => setYear(e.target.value)} />
        <span className="text-sm text-slate-500">年度期初余额（借方合计 {fmtMoney(totalD)} / 贷方合计 {fmtMoney(totalC)}）</span>
        {balanced ? <Badge color="green">试算平衡</Badge> : <Badge color="red">不平衡</Badge>}
        <div className="flex-1" />
        <button
          className="btn-primary"
          disabled={!balanced}
          onClick={async () => {
            const rows = Object.entries(edits).map(([id, v]) => ({
              account_id: Number(id),
              debit: Number(v.debit ?? 0) || 0,
              credit: Number(v.credit ?? 0) || 0,
            }));
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
                  <td className="td">{r.code} {r.name}</td>
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

function CashflowMap() {
  const [rows, setRows] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ account_id: "", cashflow_code: "" });
  const msg = useMsg();
  const load = () => {
    apiGet("/api/settings/cashflow-map").then(setRows).catch(() => {});
    apiGet("/api/accounts").then(setAccounts).catch(() => {});
    apiGet("/api/settings/cashflow-items").then(setItems).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  return (
    <div className="card">
      <div className="flex gap-3 p-4 border-b border-slate-200">
        <select className="input w-72" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })}>
          <option value="">选择科目…</option>
          {accounts.map((a) => (
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
      {msg.node && <div className="p-4">{msg.node}</div>}
      <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0">
            <tr>
              <th className="th">对方科目</th>
              <th className="th">现金流量项目</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
                <td className="td">
                  <span className="font-mono text-xs text-slate-400 mr-2">{r.account_code}</span>
                  {r.account_name}
                </td>
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
                <td className="td-num">{fmtMoney(f.original_value)}</td>
                <td className="td-num">{(f.residual_rate * 100).toFixed(0)}%</td>
                <td className="td-num">{f.life_months}</td>
                <td className="td-num font-medium">{fmtMoney(f.monthly_depreciation)}</td>
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
                <td className="td-num">{fmtMoney(f.original_value)}</td>
                <td className="td-num">{f.amort_months}</td>
                <td className="td-num font-medium">{fmtMoney(f.monthly_amortization)}</td>
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
