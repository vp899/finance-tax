import "./globals.css";
import Nav from "@/components/Nav";

export const metadata = {
  title: "财务报税系统",
  description: "凭证 · 账簿 · 报表 · 结转 · 报税",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body className="font-sans text-slate-800">
        <div className="flex min-h-screen">
          <Nav />
          <main className="flex-1 min-w-0">
            <div className="max-w-[1400px] mx-auto px-6 py-6">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
