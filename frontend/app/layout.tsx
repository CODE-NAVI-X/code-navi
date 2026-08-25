import type { Metadata } from "next";
import "./globals.css";
// KaTeX math rendering for the knowledge-PPT presentation feature.
import "katex/dist/katex.min.css";
import { AuthProvider } from "@/lib/context/auth-context";

export const metadata: Metadata = {
  title: "Code Navi",
  description: "面向学习、实践与科研探索的智能辅助平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
