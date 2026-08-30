"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { BookOpen, BriefcaseBusiness, Microscope, Users } from "lucide-react";
import { WorkspaceContextBar } from "@/components/WorkspaceContextBar";
import { AuthNav } from "@/components/AuthNav";

const modules = [
  { href: "/", label: "工作台", section: "workbench", icon: BriefcaseBusiness },
  { href: "/learning", label: "学习", match: "learning", icon: BookOpen },
  { href: "/research", label: "科研", match: "research", icon: Microscope },
  { href: "/classes", label: "班级", match: "classes", icon: Users },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isWorkbenchPath =
    pathname === "/" ||
    pathname.startsWith("/workspaces/") ||
    pathname.startsWith("/tasks/");

  return (
    <div className="min-h-screen bg-[var(--app-surface)] text-[var(--app-foreground)]">
      <header className="sticky top-0 z-[70] border-b border-[var(--app-border)] bg-[var(--app-header)] shadow-[var(--app-shadow)] backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1920px] items-center justify-between gap-2 px-2 sm:gap-4 sm:px-6">
          <Link href="/" className="flex min-w-0 items-center gap-2.5" aria-label="Code Navi 首页">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-950 font-mono text-xs font-bold text-white sm:h-9 sm:w-9 sm:rounded-xl sm:text-sm dark:bg-white dark:text-zinc-950">
              CN
            </span>
            <span className="hidden truncate text-sm font-bold tracking-tight min-[430px]:inline">Code Navi</span>
          </Link>

          <div className="flex items-center gap-2 sm:gap-4">
            <nav aria-label="主要模块" className="grid min-w-0 grid-cols-4 rounded-xl border border-[var(--app-border)] bg-[var(--app-card)] p-0.5 shadow-sm sm:p-1">
              {modules.map(({ href, label, icon: Icon, ...module }) => {
                const active =
                  "section" in module
                    ? isWorkbenchPath
                    : pathname === `/${module.match}` || pathname.startsWith(`/${module.match}/`);
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`inline-flex min-w-0 items-center justify-center gap-1 rounded-lg px-2 py-2 text-xs font-semibold whitespace-nowrap transition min-[360px]:px-2.5 sm:min-w-24 sm:gap-1.5 sm:px-3 ${
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
            <Suspense fallback={null}>
              <AuthNav />
            </Suspense>
          </div>
        </div>
      </header>
      <Suspense fallback={null}>
        <WorkspaceContextBar />
      </Suspense>
      {children}
    </div>
  );
}
