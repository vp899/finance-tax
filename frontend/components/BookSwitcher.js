"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, currentBookId, setBookId } from "@/lib/api";

/**
 * 账套切换器：切换后整页刷新，让所有页面按新账套重新拉取数据。
 */
export default function BookSwitcher() {
  const [books, setBooks] = useState([]);
  const [cur, setCur] = useState("default");

  useEffect(() => {
    setCur(currentBookId());
    apiGet("/api/booksets")
      .then(setBooks)
      .catch(() => {});
  }, []);

  const onChange = (id) => {
    setBookId(id);
    setCur(id);
    if (typeof window !== "undefined") window.location.reload();
  };

  return (
    <div className="px-4 py-3 border-b border-slate-800 space-y-2">
      <div className="text-[11px] text-slate-500 uppercase tracking-wide">当前账套</div>
      <select
        className="w-full bg-slate-800 text-slate-100 text-sm rounded-md px-2 py-1.5 border border-slate-700 focus:outline-none"
        value={cur}
        onChange={(e) => onChange(e.target.value)}
      >
        {books.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
            {b.is_default ? "（默认）" : ""}
          </option>
        ))}
        {!books.some((b) => b.id === cur) && <option value={cur}>{cur}</option>}
      </select>
      <Link href="/booksets" className="block text-xs text-slate-400 hover:text-white">
        账套管理 →
      </Link>
    </div>
  );
}
