"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import BookSwitcher from "@/components/BookSwitcher";

const items = [
  { href: "/", label: "仪表盘", icon: "📊" },
  { href: "/vouchers", label: "凭证管理", icon: "📝" },
  { href: "/books", label: "账簿查询", icon: "📚" },
  { href: "/reports", label: "财务报表", icon: "📈" },
  { href: "/carryover", label: "结转与结账", icon: "🔄" },
  { href: "/settings", label: "财税设置", icon: "⚙️" },
  { href: "/data", label: "数据管理", icon: "💾" },
  { href: "/booksets", label: "账套管理", icon: "🗂" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 bg-slate-900 text-slate-200 flex flex-col">
      <div className="px-5 py-5 border-b border-slate-800">
        <div className="text-lg font-bold text-white tracking-wide">财务报税系统</div>
        <div className="text-xs text-slate-400 mt-1">小企业会计准则 · SQLite</div>
      </div>
      <BookSwitcher />
      <nav className="flex-1 py-3">
        {items.map((it) => {
          const active =
            it.href === "/"
              ? pathname === "/"
              : pathname.startsWith(it.href);
          return (
            <Link
              key={it.href}
              href={it.href}
              className={`flex items-center gap-3 px-5 py-2.5 text-sm transition-colors
                ${active
                  ? "bg-brand-600/90 text-white font-medium border-l-4 border-brand-300"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white border-l-4 border-transparent"}`}
            >
              <span className="text-base">{it.icon}</span>
              {it.label}
            </Link>
          );
        })}
      </nav>
      <div className="px-5 py-4 border-t border-slate-800 text-xs text-slate-500">
        FastAPI + Next.js
      </div>
    </aside>
  );
}
