"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, fmtMoney, limitDecimals } from "@/lib/api";

/* 科目智能补全：支持编码、名称、拼音首字母（如 yhck → 银行存款） */
export function AccountCombobox({ value, onSelect, placeholder }) {
  const [text, setText] = useState(value ? `${value.code} ${value.name}` : "");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef(null);
  const timer = useRef(null);
  const blurTimer = useRef(null);

  useEffect(() => {
    if (value) setText(`${value.code} ${value.name}`);
  }, [value]);

  useEffect(() => {
    const h = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const search = (q) => {
    setLoading(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await apiGet(`/api/vouchers/suggest?q=${encodeURIComponent(q)}`);
        setItems(r.accounts || []);
        setOpen(true);
        setHi(0);
      } catch (_) {
        setItems([]);
      } finally {
        setLoading(false);
      }
    }, 120);
  };

  const pick = (a) => {
    setText(`${a.code} ${a.name}`);
    setOpen(false);
    onSelect?.(a);
  };

  return (
    <div className="relative" ref={boxRef}>
      <input
        className="input"
        value={text}
        placeholder={placeholder || "输入编码/名称/拼音首字母"}
        onFocus={(e) => {
          clearTimeout(blurTimer.current);
          search(e.target.value.split(" ")[0] || "");
          e.target.select();
        }}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 150);
        }}
        onChange={(e) => {
          setText(e.target.value);
          search(e.target.value);
        }}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHi((h) => Math.min(h + 1, items.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHi((h) => Math.max(h - 1, 0));
          } else if (e.key === "Enter" && items[hi]) {
            e.preventDefault();
            pick(items[hi]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && items.length > 0 && (
        <div className="absolute z-40 mt-1 w-full max-h-64 overflow-auto bg-white border border-slate-200 rounded-lg shadow-lg">
          {items.map((a, i) => (
            <div
              key={a.id}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(a);
              }}
              onMouseEnter={() => setHi(i)}
              className={`px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-2
                ${i === hi ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50"}`}
            >
              <div>
                <span className="font-mono text-xs text-slate-400 mr-2">{a.code}</span>
                {a.name}
                {!a.is_leaf && (
                  <span className="ml-2 text-xs text-amber-600">（非末级）</span>
                )}
              </div>
              <div className="text-xs text-slate-400 tabular-nums">
                余额 {fmtMoney(a.balance)}
              </div>
            </div>
          ))}
        </div>
      )}
      {open && loading && (
        <div className="absolute z-40 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs text-slate-400">
          搜索中…
        </div>
      )}
    </div>
  );
}

/* 摘要补全 */
function SummaryInput({ value, onChange }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  const search = (q) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await apiGet(`/api/vouchers/suggest?q=${encodeURIComponent(q)}`);
        setItems(r.summaries || []);
        setOpen(true);
      } catch (_) {}
    }, 150);
  };

  return (
    <div className="relative">
      <input
        className="input"
        value={value}
        placeholder="摘要"
        onFocus={(e) => search(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          onChange(e.target.value);
          search(e.target.value);
        }}
      />
      {open && items.length > 0 && (
        <div className="absolute z-40 mt-1 w-full max-h-48 overflow-auto bg-white border border-slate-200 rounded-lg shadow-lg">
          {items.map((s, i) => (
            <div
              key={i}
              onMouseDown={(e) => {
                e.preventDefault();
                onChange(s);
                setOpen(false);
              }}
              className="px-3 py-1.5 text-sm cursor-pointer hover:bg-slate-50 truncate"
            >
              {s}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const emptyLine = () => ({
  key: Math.random().toString(36).slice(2),
  summary: "",
  account: null,
  debit: "",
  credit: "",
  quantity: "",
  unit: "",
});

/* 凭证编辑器（新增/编辑） */
export default function VoucherEditor({ voucher, onSaved, onCancel }) {
  const [date, setDate] = useState(voucher?.date || new Date().toISOString().slice(0, 10));
  const [vtype, setVtype] = useState(voucher?.vtype || "记");
  const [remark, setRemark] = useState(voucher?.remark || "");
  const [attach, setAttach] = useState(voucher?.attachment_count || 0);
  const [lines, setLines] = useState(
    voucher?.entries?.length
      ? voucher.entries.map((e) => ({
          key: Math.random().toString(36).slice(2),
          summary: e.summary,
          account: { id: e.account_id, code: e.account_code, name: e.account_name },
          debit: e.debit ? String(e.debit) : "",
          credit: e.credit ? String(e.credit) : "",
          quantity: e.quantity ? String(e.quantity) : "",
          unit: e.unit || "",
        }))
      : [emptyLine(), emptyLine()]
  );
  const [types, setTypes] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet("/api/settings/voucher-types").then(setTypes).catch(() => {});
  }, []);

  const setLine = (key, patch) =>
    setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const totalD = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalC = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const balanced = Math.abs(totalD - totalC) < 0.005 && totalD > 0;

  const save = async () => {
    setError("");
    const entries = lines
      .filter((l) => l.account && (Number(l.debit) || Number(l.credit)))
      .map((l) => ({
        account_id: l.account.id,
        summary: l.summary,
        debit: Number(l.debit) || 0,
        credit: Number(l.credit) || 0,
        quantity: Number(l.quantity) || 0,
        unit: l.unit,
      }));
    if (!entries.length) {
      setError("请至少录入一行有效分录（选择科目并填写金额）");
      return;
    }
    setSaving(true);
    try {
      const { apiPost, apiPut } = await import("@/lib/api");
      const body = {
        date,
        vtype,
        remark,
        attachment_count: Number(attach) || 0,
        entries,
      };
      const r = voucher?.id
        ? await apiPut(`/api/vouchers/${voucher.id}`, body)
        : await apiPost("/api/vouchers", body);
      onSaved?.(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className="label">凭证日期</label>
          <input type="date" className="input" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div>
          <label className="label">凭证类型</label>
          <select className="input" value={vtype} onChange={(e) => setVtype(e.target.value)}>
            {(types.length ? types : [{ prefix: "记", name: "记账凭证" }]).map((t) => (
              <option key={t.prefix} value={t.prefix}>
                {t.name}（{t.prefix}）
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">附件数</label>
          <input
            type="number"
            className="input"
            value={attach}
            min={0}
            onChange={(e) => setAttach(e.target.value)}
          />
        </div>
        <div>
          <label className="label">备注</label>
          <input className="input" value={remark} onChange={(e) => setRemark(e.target.value)} />
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th w-8"></th>
              <th className="th w-48">摘要</th>
              <th className="th">会计科目</th>
              <th className="th w-32 text-right">借方金额</th>
              <th className="th w-32 text-right">贷方金额</th>
              <th className="th w-20">数量</th>
              <th className="th w-20">单位</th>
              <th className="th w-10"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={l.key} className="hover:bg-slate-50/60">
                <td className="td text-slate-400 text-xs">{i + 1}</td>
                <td className="td p-1">
                  <SummaryInput value={l.summary} onChange={(v) => setLine(l.key, { summary: v })} />
                </td>
                <td className="td p-1">
                  <AccountCombobox
                    value={l.account}
                    onSelect={(a) => setLine(l.key, { account: a })}
                  />
                </td>
                <td className="td p-1">
                  <input
                    className="input text-right tabular-nums"
                    value={l.debit}
                    placeholder="0.00"
                    onFocus={(e) => e.target.select()}
                    onChange={(e) => {
                      const v = e.target.value.replace(/[^\d.]/g, "");
                      setLine(l.key, { debit: v, credit: v ? "" : l.credit });
                    }}
                  />
                </td>
                <td className="td p-1">
                  <input
                    className="input text-right tabular-nums"
                    value={l.credit}
                    placeholder="0.00"
                    onFocus={(e) => e.target.select()}
                    onChange={(e) => {
                      const v = e.target.value.replace(/[^\d.]/g, "");
                      setLine(l.key, { credit: v, debit: v ? "" : l.debit });
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && i === lines.length - 1) {
                        setLines((ls) => [...ls, emptyLine()]);
                      }
                    }}
                  />
                </td>
                <td className="td p-1">
                  <input
                    className="input text-right tabular-nums"
                    value={l.quantity}
                    onChange={(e) => setLine(l.key, { quantity: limitDecimals(e.target.value, 2) })}
                  />
                </td>
                <td className="td p-1">
                  <input
                    className="input"
                    value={l.unit}
                    onChange={(e) => setLine(l.key, { unit: e.target.value })}
                  />
                </td>
                <td className="td text-center">
                  <button
                    className="text-slate-300 hover:text-rose-500"
                    onClick={() => setLines((ls) => (ls.length > 1 ? ls.filter((x) => x.key !== l.key) : ls))}
                    title="删除本行"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-slate-50">
              <td className="td" colSpan={3}>
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => setLines((ls) => [...ls, emptyLine()])}
                >
                  ＋ 添加分录
                </button>
              </td>
              <td className="td-num font-semibold">{fmtMoney(totalD)}</td>
              <td className="td-num font-semibold">{fmtMoney(totalC)}</td>
              <td className="td" colSpan={3}></td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm">
          {totalD === 0 && totalC === 0 ? (
            <span className="text-slate-400">等待录入…</span>
          ) : balanced ? (
            <span className="text-emerald-600">✓ 借贷平衡</span>
          ) : (
            <span className="text-rose-600">
              借贷不平衡（差额 {fmtMoney(Math.abs(totalD - totalC))}）
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={onCancel}>
            取消
          </button>
          <button className="btn-primary" onClick={save} disabled={saving || !balanced}>
            {saving ? "保存中…" : "保存凭证"}
          </button>
        </div>
      </div>
      {error && (
        <div className="border border-rose-200 bg-rose-50 text-rose-700 rounded-lg px-4 py-2.5 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
