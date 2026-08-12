"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Code2, Microscope } from "lucide-react";

const modules = [
  { href: "/learning", label: "学习", match: "learning", icon: BookOpen },
  { href: "/practice", label: "练习", match: "practice", icon: Code2 },
  { href: "/research", label: "科研", match: "research", icon: Microscope },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[var(--app-surface)] text-[var(--app-foreground)]">
      <header className="sticky top-0 z-[70] border-b border-[var(--app-border)] bg-[var(--app-header)] backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1920px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link href="/learning" className="flex min-w-0 items-center gap-2.5" aria-label="Code Navi 首页">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-950 font-mono text-sm font-bold text-white dark:bg-white dark:text-zinc-950">
              CN
            </span>
            <span className="truncate text-sm font-bold tracking-tight">Code Navi</span>
          </Link>

          <nav aria-label="主要模块" className="grid grid-cols-3 rounded-xl border border-[var(--app-border)] bg-white/70 p-1 shadow-sm dark:bg-zinc-900/70">
            {modules.map(({ href, label, match, icon: Icon }) => {
              const active = pathname.includes(`/${match}`);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`inline-flex min-w-16 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition sm:min-w-24 ${
                    active
                      ? "bg-slate-950 text-white shadow-sm dark:bg-white dark:text-zinc-950"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.7} />
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}
