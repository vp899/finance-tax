"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, fmtMoney, useSelMonth } from "@/lib/api";
import { Badge, Money } from "@/components/ui";

export default function Dashboard() {
  const [period] = useSelMonth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [inc, bs, vs, tb] = await Promise.all([
          apiGet(`/api/reports/income?period=${period}&mode=month`),
          apiGet(`/api/reports/balance-sheet?period=${period}`),
          apiGet(`/api/vouchers/summary?from_period=${period}&to_period=${period}`),
          apiGet(`/api/books/trial-balance?period=${period}`),
        ]);
        const imap = Object.fromEntries(inc.rows.map((r) => [r.name, r]));
        const bmap = Object.fromEntries(bs.rows.map((r) => [r.name, r]));
        setData({ inc, bs, vs, tb, imap, bmap });
      } catch (e) {
        setError(e.message);
      }
    })();
  }, [period]);

  const cards = [
    { label: "本期营业收入", value: data?.imap?.["一、营业收入"]?.current, color: "text-emerald-600" },
    { label: "本期净利润", value: data?.imap?.["四、净利润（净亏损以“-”号填列）"]?.current, color: "text-brand-600" },
    { label: "资产总计", value: data?.bmap?.["资产总计"]?.ending, color: "text-slate-800" },
    { label: "负债合计", value: data?.bmap?.["负债合计"]?.ending, color: "text-amber-600" },
    { label: "本期凭证数", value: data?.vs?.count, color: "text-slate-800", int: true },
    { label: "未分配利润", value: data?.bmap?.["未分配利润"]?.ending, color: "text-slate-800" },
  ];

  const links = [
    { href: "/vouchers", title: "录入凭证", desc: "新增 / 查看 / 凭证汇总表", icon: "📝" },
    { href: "/carryover", title: "月末结转", desc: "折旧、摊销、损益结转、结账", icon: "🔄" },
    { href: "/reports", title: "生成报表", desc: "资产负债表 / 利润表 / 现金流量表", icon: "📈" },
    { href: "/settings", title: "财税设置", desc: "科目期初 / 税率 / 现金流量对照", icon: "⚙️" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">工作台</h1>
          <p className="text-slate-500 text-sm mt-1">会计期间 {period} · 小规模纳税人 · 2013 小企业会计准则</p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <>
              <Badge color={data.tb?.balanced ? "green" : "red"}>
                试算{data.tb?.balanced ? "平衡" : "不平衡"}
              </Badge>
              <Badge color={data.bs?.balanced ? "green" : "red"}>
                资产负债表{data.bs?.balanced ? "平衡" : "不平衡"}
              </Badge>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="border border-rose-200 bg-rose-50 text-rose-700 rounded-lg px-4 py-3 text-sm">
          无法连接后端服务：{error}（请确认 FastAPI 已在 8000 端口启动）
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="card p-4">
            <div className="text-xs text-slate-500">{c.label}</div>
            <div className={`mt-1.5 text-xl font-semibold ${c.color}`}>
              {data ? (
                c.int ? c.value : <Money v={c.value} />
              ) : (
                <span className="text-slate-300">…</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="card p-5 hover:shadow-md transition-shadow group">
            <div className="text-2xl">{l.icon}</div>
            <div className="mt-2 font-semibold text-slate-800 group-hover:text-brand-700">{l.title}</div>
            <div className="text-sm text-slate-500 mt-1">{l.desc}</div>
          </Link>
        ))}
      </div>

      {data && (
        <div className="card p-5">
          <h2 className="font-semibold text-slate-800 mb-3">本期经营概览（{period}）</h2>
          <div className="grid md:grid-cols-3 gap-x-8 gap-y-2 text-sm">
            {["一、营业收入", "　减：营业成本", "　　　营业税金及附加", "　　　管理费用",
              "三、利润总额（亏损以“-”号填列）", "四、净利润（净亏损以“-”号填列）"].map((n) => {
              const r = data.imap[n];
              if (!r) return null;
              return (
                <div key={n} className="flex justify-between border-b border-dashed border-slate-200 py-1.5">
                  <span className="text-slate-600">{n.replace(/^[　\s]+/, "")}</span>
                  <span className={`tabular-nums ${r.type === "calc" ? "font-semibold text-slate-900" : ""}`}>
                    <Money v={r.current} />
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
