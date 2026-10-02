"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  apiDel, apiGet, apiPost, apiPut, apiUpload, downloadUrl, fmtMoney,
} from "@/lib/api";
import { Alert, Badge, Modal } from "@/components/ui";

const CATEGORY_OPTIONS = [
  ["asset", "资产"], ["liability", "负债"], ["equity", "权益"],
  ["cost", "成本"], ["income", "损益-收入"], ["expense", "损益-费用"],
];

const AUX_DIMENSIONS = [
  ["aux_project", "项目"], ["aux_customer", "客户"], ["aux_supplier", "供应商"],
  ["aux_dept", "部门"], ["aux_employee", "员工"], ["aux_inventory", "存货"],
];

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

/* ---------------- 科目表管理 ---------------- */

export default function AccountManager() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  const [asOf, setAsOf] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [sel, setSel] = useState({});
  const [editing, setEditing] = useState(null); // {mode:"new"|"edit"|"child", data}
  const [clearOpen, setClearOpen] = useState(false);
  const [settings, setSettings] = useState({});
  const msg = useMsg();
  const chartFile = useRef(null);
  const openingFile = useRef(null);

  const load = useCallback(() => {
    apiGet(`/api/accounts?as_of=${asOf}`).then(setRows).catch((e) => msg.setError(e.message));
    apiGet("/api/settings").then(setSettings).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asOf]);
  useEffect(load, [load]);

  const selectedIds = () => Object.keys(sel).filter((k) => sel[k]).map(Number);

  const batch = async (action) => {
    const ids = selectedIds();
    if (!ids.length) {
      msg.setError("请先勾选科目");
      return;
    }
    if (action === "delete" && !confirm(`确认删除勾选的 ${ids.length} 个科目？有发生额或期初的科目会自动跳过。`)) return;
    try {
      const r = await apiPost("/api/accounts/batch", { action, ids });
      const bad = r.results.filter((x) => !x.ok);
      msg.setOk(`成功 ${r.ok_count} 个${bad.length ? `，失败 ${bad.length} 个（${bad.map((b) => b.message).join("；")}）` : ""}`);
      setSel({});
      load();
    } catch (e) {
      msg.setError(e.message);
    }
  };

  const setDisabled = async (a, disabled) => {
    try {
      await apiPut(`/api/accounts/${a.id}`, { is_disabled: disabled });
      load();
    } catch (e) {
      msg.setError(e.message);
    }
  };

  const removeAccount = async (a) => {
    if (!confirm(`确认删除科目 ${a.code} ${a.name}？`)) return;
    try {
      await apiDel(`/api/accounts/${a.id}`);
      msg.setOk("科目已删除");
      load();
    } catch (e) {
      msg.setError(e.message);
    }
  };

  const importChart = async (file) => {
    if (!file) return;
    try {
      const r = await apiUpload("/api/accounts/import", file);
      msg.setOk(`科目表导入完成：新增 ${r.created}，更新 ${r.updated}${r.errors?.length ? `，失败 ${r.errors.length} 行` : ""}`);
      load();
    } catch (e) {
      msg.setError(e.message);
    }
  };

  const importOpenings = async (file) => {
    if (!file) return;
    try {
      const r = await apiUpload(`/api/accounts/openings/import?year=${year}`, file);
      msg.setOk(`科目期初导入完成：${r.imported} 行（借 ${fmtMoney(r.total_debit)} / 贷 ${fmtMoney(r.total_credit)}）${r.errors?.length ? `，失败 ${r.errors.length} 行` : ""}`);
      load();
    } catch (e) {
      msg.setError(e.message);
    }
  };

  const filtered = rows.filter(
    (a) => !q || a.code.includes(q) || a.name.includes(q) ||
      (a.pinyin || "").toLowerCase().includes(q.toLowerCase())
  );
  const allChecked = filtered.length > 0 && filtered.every((a) => sel[a.id]);

  return (
    <div className="card">
      {msg.node}
      <div className="flex flex-wrap items-center gap-2 p-4 border-b border-slate-200">
        <button className="btn-primary" onClick={() => setEditing({
          mode: "new",
          data: { code: "", name: "", parent_code: "", direction: "D", category: "asset",
                  currency: "CNY", unit: "", quantity_accounting: false, remark: "" },
        })}>
          ＋ 新增科目
        </button>
        <button className="btn-ghost" onClick={() => chartFile.current?.click()}>导入科目表</button>
        <a className="btn-ghost" href={downloadUrl("/api/accounts/export.xlsx")}>导出科目表</a>
        <button className="btn-ghost" onClick={() => openingFile.current?.click()}>导入科目期初</button>
        <a className="btn-ghost" href={downloadUrl(`/api/accounts/openings/export.xlsx?year=${year}`)}>导出科目期初</a>
        <button className="btn-ghost text-rose-600" onClick={() => setClearOpen(true)}>数据清零</button>
        <span className="w-px h-6 bg-slate-200 mx-1" />
        <button className="btn-ghost" onClick={() => batch("enable")}>批量启用</button>
        <button className="btn-ghost" onClick={() => batch("disable")}>批量禁用</button>
        <button className="btn-ghost text-rose-600" onClick={() => batch("delete")}>批量删除</button>
        <div className="flex-1" />
        <label className="text-xs text-slate-500">
          期初年月
          <input type="month" className="input w-36 ml-2" value={asOf}
                 onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <label className="text-xs text-slate-500">
          期初年度
          <input className="input w-24 ml-2" value={year}
                 onChange={(e) => setYear(e.target.value.replace(/[^\d]/g, ""))} />
        </label>
        <input className="input w-48" placeholder="搜索编码 / 名称 / 拼音"
               value={q} onChange={(e) => setQ(e.target.value)} />
        <input ref={chartFile} type="file" accept=".xlsx" hidden
               onChange={(e) => { importChart(e.target.files?.[0]); e.target.value = ""; }} />
        <input ref={openingFile} type="file" accept=".xlsx" hidden
               onChange={(e) => { importOpenings(e.target.files?.[0]); e.target.value = ""; }} />
      </div>

      <div className="overflow-x-auto max-h-[65vh] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-white">
            <tr>
              <th className="th w-10">
                <input type="checkbox" checked={allChecked}
                       onChange={(e) => {
                         const next = { ...sel };
                         filtered.forEach((a) => { next[a.id] = e.target.checked; });
                         setSel(next);
                       }} />
              </th>
              <th className="th">科目编码</th>
              <th className="th">科目名称</th>
              <th className="th">核算类型</th>
              <th className="th">计量单位</th>
              <th className="th">借贷方向</th>
              <th className="th text-right">期初余额({asOf})</th>
              <th className="th">状态</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a) => (
              <tr key={a.id} className={`hover:bg-slate-50 ${a.is_disabled ? "opacity-50" : ""}`}>
                <td className="td text-center">
                  <input type="checkbox" checked={!!sel[a.id]}
                         onChange={(e) => setSel({ ...sel, [a.id]: e.target.checked })} />
                </td>
                <td className="td font-mono text-xs">
                  <span style={{ paddingLeft: Math.max(0, a.level - 1) * 16 }}>{a.code}</span>
                </td>
                <td className="td">
                  {a.name}
                  {a.quantity_accounting && <Badge color="blue">数量</Badge>}
                  {AUX_DIMENSIONS.some(([f]) => a[f]) && <Badge color="amber">辅助</Badge>}
                </td>
                <td className="td text-xs">{a.category_name}</td>
                <td className="td text-xs">{a.unit || ""}</td>
                <td className="td text-xs">{a.direction === "D" ? "借" : "贷"}</td>
                <td className="td-num">
                  {a.opening && (a.opening.debit || a.opening.credit)
                    ? <>{fmtMoney(a.opening.debit || a.opening.credit)} {a.opening.debit ? "借" : "贷"}</>
                    : ""}
                </td>
                <td className="td">
                  {a.is_disabled ? <Badge color="red">停用</Badge> : <Badge color="green">启用</Badge>}
                </td>
                <td className="td text-right whitespace-nowrap text-xs">
                  <button className="text-brand-600 hover:underline mr-2"
                          onClick={() => setEditing({ mode: "edit", data: a })}>
                    编辑
                  </button>
                  <button className="text-brand-600 hover:underline mr-2"
                          onClick={() => setEditing({
                            mode: "child",
                            data: { code: "", name: "", parent_code: a.code, direction: a.direction,
                                    category: a.category, currency: a.currency || "CNY",
                                    unit: a.unit || "", quantity_accounting: false, remark: "" },
                          })}>
                    添加下级
                  </button>
                  <button className="text-slate-500 hover:underline mr-2"
                          onClick={() => setDisabled(a, !a.is_disabled)}>
                    {a.is_disabled ? "启用" : "禁用"}
                  </button>
                  <button className="text-rose-600 hover:underline"
                          onClick={() => removeAccount(a)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <AccountDialog
          mode={editing.mode}
          initial={editing.data}
          accounts={rows}
          settings={settings}
          onClose={() => setEditing(null)}
          onSaved={(msgText) => {
            setEditing(null);
            msg.setOk(msgText);
            load();
          }}
          onError={(m) => msg.setError(m)}
        />
      )}

      {clearOpen && (
        <ClearDialog
          onClose={() => setClearOpen(false)}
          onDone={(m) => {
            setClearOpen(false);
            msg.setOk(m);
            load();
          }}
          onError={(m) => msg.setError(m)}
        />
      )}
    </div>
  );
}

/* ---------------- 科目编辑对话框 ---------------- */

function AccountDialog({ mode, initial, accounts, settings, onClose, onSaved, onError }) {
  const [form, setForm] = useState({
    ...initial,
    aux_project: !!initial.aux_project,
    aux_customer: !!initial.aux_customer,
    aux_supplier: !!initial.aux_supplier,
    aux_dept: !!initial.aux_dept,
    aux_employee: !!initial.aux_employee,
    aux_inventory: !!initial.aux_inventory,
    quantity_accounting: !!initial.quantity_accounting,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (patch) => setForm({ ...form, ...patch });

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      if (mode === "edit") {
        const { id, name, direction, category, currency, unit, remark, pinyin,
                quantity_accounting, parent_code } = form;
        await apiPut(`/api/accounts/${id}`, {
          name, direction, category, currency, unit, remark, pinyin,
          parent_code, quantity_accounting,
          aux_project: form.aux_project, aux_customer: form.aux_customer,
          aux_supplier: form.aux_supplier, aux_dept: form.aux_dept,
          aux_employee: form.aux_employee, aux_inventory: form.aux_inventory,
        });
        onSaved("科目已保存");
      } else {
        await apiPost("/api/accounts", {
          code: form.code, name: form.name, parent_code: form.parent_code,
          direction: form.direction, category: form.category, currency: form.currency,
          unit: form.unit, remark: form.remark, pinyin: form.pinyin,
          quantity_accounting: form.quantity_accounting,
          aux_project: form.aux_project, aux_customer: form.aux_customer,
          aux_supplier: form.aux_supplier, aux_dept: form.aux_dept,
          aux_employee: form.aux_employee, aux_inventory: form.aux_inventory,
        });
        onSaved("科目已新增");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open wide title={mode === "edit" ? `编辑科目 ${initial.code}` : "新增科目"} onClose={onClose}>
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="label">科目编码 *</label>
            <input className="input" value={form.code} disabled={mode === "edit"}
                   onChange={(e) => set({ code: e.target.value.replace(/\s/g, "") })} />
          </div>
          <div>
            <label className="label">科目名称 *</label>
            <input className="input" value={form.name} onChange={(e) => set({ name: e.target.value })} />
          </div>
          <div>
            <label className="label">上级科目</label>
            <select className="input" value={form.parent_code || ""}
                    onChange={(e) => set({ parent_code: e.target.value })}>
              <option value="">（无 / 一级科目）</option>
              {accounts.filter((a) => a.code !== form.code).map((a) => (
                <option key={a.id} value={a.code}>
                  {"　".repeat(Math.max(0, a.level - 1))}{a.code} {a.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">核算类型</label>
            <select className="input" value={form.category}
                    onChange={(e) => set({ category: e.target.value })}>
              {CATEGORY_OPTIONS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </div>
          <div>
            <label className="label">借贷方向</label>
            <select className="input" value={form.direction}
                    onChange={(e) => set({ direction: e.target.value })}>
              <option value="D">借</option>
              <option value="C">贷</option>
            </select>
          </div>
          <div>
            <label className="label">默认币种</label>
            <input className="input" value={form.currency || "CNY"}
                   onChange={(e) => set({ currency: e.target.value })} />
          </div>
          <div>
            <label className="label">计量单位</label>
            <input className="input" value={form.unit || ""}
                   onChange={(e) => set({ unit: e.target.value })} />
          </div>
          <div>
            <label className="label">拼音首字母（智能补全）</label>
            <input className="input" value={form.pinyin || ""}
                   onChange={(e) => set({ pinyin: e.target.value })} />
          </div>
          <div>
            <label className="label">备注</label>
            <input className="input" value={form.remark || ""}
                   onChange={(e) => set({ remark: e.target.value })} />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 pt-1">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.quantity_accounting}
                   onChange={(e) => set({ quantity_accounting: e.target.checked })} />
            数量核算
          </label>
          <span className="w-px h-5 bg-slate-200" />
          <span className="text-xs text-slate-500">辅助核算：</span>
          {AUX_DIMENSIONS.map(([field, label]) => {
            const globalOn = settings[`aux_switch_${field.replace("aux_", "")}`] !== "0";
            return (
              <label key={field} className={`flex items-center gap-1.5 text-sm ${globalOn ? "" : "opacity-40"}`}>
                <input type="checkbox" checked={form[field] && globalOn} disabled={!globalOn}
                       onChange={(e) => set({ [field]: e.target.checked })} />
                {label}
              </label>
            );
          })}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-primary" onClick={save} disabled={busy}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ---------------- 数据清零 ---------------- */

function ClearDialog({ onClose, onDone, onError }) {
  const [scope, setScope] = useState({
    vouchers: true, carryover: true, periods: true, openings: false,
  });
  const [confirmFlag, setConfirmFlag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await apiPost("/api/accounts/data/clear", {
        confirm: true,
        scope: Object.keys(scope).filter((k) => scope[k]),
      });
      onDone(`数据清零完成：凭证 ${r.cleared.vouchers ?? 0} 张、结转记录 ${r.cleared.carryover_records ?? 0} 条已清空`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title="数据清零" onClose={onClose}>
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Alert type="info">
          数据清零用于重新建账：清空业务数据但保留科目表与系统设置。<b>操作不可恢复</b>，建议先在【数据管理】备份数据库。
        </Alert>
        <div className="space-y-2">
          {[
            ["vouchers", "凭证（含分录）"],
            ["carryover", "结转记录"],
            ["periods", "会计期间（结账状态）"],
            ["openings", "科目期初余额"],
          ].map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={scope[k]}
                     onChange={(e) => setScope({ ...scope, [k]: e.target.checked })} />
              {label}
            </label>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-rose-600">
          <input type="checkbox" checked={confirmFlag}
                 onChange={(e) => setConfirmFlag(e.target.checked)} />
          我已了解数据清零不可恢复，确认执行
        </label>
        <div className="flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-primary bg-rose-600 hover:bg-rose-700"
                  disabled={!confirmFlag || busy} onClick={run}>
            {busy ? "清零中…" : "执行数据清零"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
