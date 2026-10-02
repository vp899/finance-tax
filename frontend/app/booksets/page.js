"use client";

import { useEffect, useState } from "react";
import { apiDel, apiGet, apiPost, apiPut, currentBookId, setBookId } from "@/lib/api";
import { Alert, Badge } from "@/components/ui";

export default function BooksetsPage() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: "", remark: "", opening_year: "", copy_from: "" });
  const [editing, setEditing] = useState(null); // {id, name, remark}
  const [msg, setMsg] = useState(null);
  const [cur, setCur] = useState("default");

  const load = () => apiGet("/api/booksets").then(setRows).catch((e) => setMsg({ type: "error", text: e.message }));
  useEffect(() => {
    setCur(currentBookId());
    load();
  }, []);

  const ok = (text) => setMsg({ type: "success", text });
  const fail = (e) => setMsg({ type: "error", text: e.message });

  const create = async () => {
    if (!form.name.trim()) return setMsg({ type: "error", text: "请填写账套名称" });
    try {
      const body = {
        name: form.name.trim(),
        remark: form.remark,
        opening_year: form.opening_year.trim(),
        copy_from: form.copy_from || "",
      };
      const r = await apiPost("/api/booksets", body);
      ok(`账套「${r.name}」已创建`);
      setForm({ name: "", remark: "", opening_year: "", copy_from: "" });
      load();
    } catch (e) {
      fail(e);
    }
  };

  const switchTo = (id) => {
    setBookId(id);
    setCur(id);
    ok("已切换账套，正在刷新…");
    setTimeout(() => window.location.reload(), 300);
  };

  const setDefault = async (id) => {
    try {
      await apiPut(`/api/booksets/${id}`, { is_default: true });
      ok("已设为默认账套");
      load();
    } catch (e) {
      fail(e);
    }
  };

  const saveEdit = async () => {
    try {
      await apiPut(`/api/booksets/${editing.id}`, { name: editing.name, remark: editing.remark });
      ok("账套信息已更新");
      setEditing(null);
      load();
    } catch (e) {
      fail(e);
    }
  };

  const remove = async (id, name) => {
    if (!confirm(`删除账套「${name}」将同时删除其全部数据，且不可恢复。确定删除吗？`)) return;
    try {
      await apiDel(`/api/booksets/${id}`);
      ok(`账套「${name}」已删除`);
      load();
    } catch (e) {
      fail(e);
    }
  };

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-slate-900">账套管理</h1>
      <p className="text-sm text-slate-500">
        每个账套是一套独立的科目 / 凭证 / 期初 / 设置数据（独立 SQLite 文件）。
        左侧下拉可随时切换当前账套；默认账套用于未指定账套的请求。
      </p>
      {msg && <Alert type={msg.type} onClose={() => setMsg(null)}>{msg.text}</Alert>}

      <div className="card p-5">
        <h2 className="font-semibold text-slate-800 mb-3">新建账套</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="label">账套名称</label>
            <input className="input w-48" placeholder="如：XX 公司 2026"
                   value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="label">科目期初年份</label>
            <input className="input w-28" placeholder="YYYY"
                   value={form.opening_year}
                   onChange={(e) => setForm({ ...form, opening_year: e.target.value.replace(/[^\d]/g, "").slice(0, 4) })} />
          </div>
          <div>
            <label className="label">复制自（可选）</label>
            <select className="input w-48" value={form.copy_from}
                    onChange={(e) => setForm({ ...form, copy_from: e.target.value })}>
              <option value="">不复制（空白账套）</option>
              {rows.map((b) => (
                <option key={b.id} value={b.id}>{b.name}（{b.id}）</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">备注</label>
            <input className="input w-48" value={form.remark}
                   onChange={(e) => setForm({ ...form, remark: e.target.value })} />
          </div>
          <button className="btn-primary" onClick={create}>创建账套</button>
        </div>
        <div className="text-xs text-slate-400 mt-2">
          空白账套会自动带标准科目表与默认设置；复制账套会连同科目、凭证、期初、设置一起复制。
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-semibold text-slate-800 mb-3">账套列表</h2>
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">账套</th>
              <th className="th">标识</th>
              <th className="th">期初年份</th>
              <th className="th text-right">科目数</th>
              <th className="th text-right">凭证数</th>
              <th className="th">状态</th>
              <th className="th text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.id} className="hover:bg-slate-50">
                <td className="td">
                  {editing?.id === b.id ? (
                    <input className="input w-40" value={editing.name}
                           onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                  ) : (
                    <>
                      <div className="font-medium text-slate-800">{b.name}</div>
                      {b.remark && <div className="text-xs text-slate-400">{b.remark}</div>}
                    </>
                  )}
                </td>
                <td className="td text-slate-500">{b.id}</td>
                <td className="td">{b.opening_year || "—"}</td>
                <td className="td text-right tabular-nums">{b.account_count}</td>
                <td className="td text-right tabular-nums">{b.voucher_count}</td>
                <td className="td">
                  {b.is_default && <Badge color="blue">默认</Badge>}
                  {b.id === cur && <Badge color="green">当前</Badge>}
                </td>
                <td className="td text-right space-x-2 whitespace-nowrap">
                  {editing?.id === b.id ? (
                    <>
                      <button className="text-emerald-600 text-xs hover:underline" onClick={saveEdit}>保存</button>
                      <button className="text-slate-400 text-xs hover:underline" onClick={() => setEditing(null)}>取消</button>
                    </>
                  ) : (
                    <>
                      {b.id !== cur && (
                        <button className="text-brand-600 text-xs hover:underline" onClick={() => switchTo(b.id)}>切换</button>
                      )}
                      <button className="text-slate-600 text-xs hover:underline"
                              onClick={() => setEditing({ id: b.id, name: b.name, remark: b.remark || "" })}>编辑</button>
                      {!b.is_default && (
                        <button className="text-amber-600 text-xs hover:underline" onClick={() => setDefault(b.id)}>设默认</button>
                      )}
                      {!b.is_default && b.id !== "default" && (
                        <button className="text-rose-600 text-xs hover:underline" onClick={() => remove(b.id, b.name)}>删除</button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
