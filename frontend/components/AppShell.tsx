"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState } from "react";
import {
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  ClipboardList,
  Code2,
  Menu,
  Microscope,
  Sparkles,
  User,
  Users,
  X,
} from "lucide-react";
import { WorkspaceContextBar } from "@/components/WorkspaceContextBar";
import { AuthNav } from "@/components/AuthNav";

interface NavItem {
  href: string;
  label: string;
  icon: typeof BriefcaseBusiness;
  exact?: boolean;
  matchPrefix?: string;
  isWorkbench?: boolean;
}

const learningSubItems: NavItem[] = [
  { href: "/learning", label: "理解与检查", icon: BookOpen, exact: true },
  { href: "/learning/practice", label: "动手实践", icon: Code2, matchPrefix: "/learning/practice" },
  { href: "/learning/portrait", label: "复盘", icon: BarChart3, matchPrefix: "/learning/portrait" },
  { href: "/learning/notebook", label: "笔记", icon: ClipboardList, matchPrefix: "/learning/notebook" },
];

function isItemActive(item: NavItem, pathname: string): boolean {
  if (item.isWorkbench) {
    return (
      pathname === "/" ||
      pathname.startsWith("/workspaces") ||
      pathname.startsWith("/tasks")
    );
  }
  if (item.exact) {
    return pathname === item.href || pathname === "/learning/explore";
  }
  if (item.matchPrefix) {
    return pathname === item.matchPrefix || pathname.startsWith(`${item.matchPrefix}/`);
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function isLearningLoopActive(pathname: string): boolean {
  return (
    pathname === "/learning" ||
    pathname.startsWith("/learning/") ||
    pathname === "/practice" ||
    pathname.startsWith("/practice/") ||
    pathname === "/portrait" ||
    pathname.startsWith("/portrait/") ||
    pathname === "/notebook" ||
    pathname.startsWith("/notebook/")
  );
}

function NavLink({
  item,
  pathname,
  onNavigate,
  className = "",
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
  className?: string;
}) {
  const active = isItemActive(item, pathname);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
        active
          ? "bg-slate-950 text-white shadow-sm dark:bg-white dark:text-zinc-950"
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white"
      } ${className}`}
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.8} />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

function NavigationTree({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  const learningActive = isLearningLoopActive(pathname);

  return (
    <nav aria-label="侧边栏主导航" className="flex flex-1 flex-col gap-1.5 px-3 py-4 overflow-y-auto">
      {/* 1. 工作台 */}
      <NavLink
        item={{ href: "/", label: "工作台", icon: BriefcaseBusiness, isWorkbench: true }}
        pathname={pathname}
        onNavigate={onNavigate}
      />

      {/* 2. 学习闭环 */}
      <div className="mt-3">
        <div className="flex items-center justify-between px-3 py-1.5 text-xs font-bold tracking-wider text-slate-400 uppercase dark:text-zinc-500">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-blue-500" strokeWidth={1.8} />
            <span>学习闭环</span>
          </div>
          {learningActive && (
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
          )}
        </div>
        <div className="mt-1 flex flex-col gap-1 pl-2 border-l-2 border-slate-200/80 ml-2 dark:border-zinc-800">
          {learningSubItems.map((subItem) => (
            <NavLink
              key={subItem.href}
              item={subItem}
              pathname={pathname}
              onNavigate={onNavigate}
              className="py-2 text-xs"
            />
          ))}
        </div>
      </div>

      {/* 3. 科研引导 */}
      <div className="mt-3">
        <NavLink
          item={{ href: "/research", label: "科研引导", icon: Microscope, matchPrefix: "/research" }}
          pathname={pathname}
          onNavigate={onNavigate}
        />
      </div>

      {/* 4. 班级 */}
      <NavLink
        item={{ href: "/classes", label: "班级", icon: Users, matchPrefix: "/classes" }}
        pathname={pathname}
        onNavigate={onNavigate}
      />

      {/* 5. 账户 */}
      <NavLink
        item={{ href: "/account", label: "账户", icon: User, matchPrefix: "/account" }}
        pathname={pathname}
        onNavigate={onNavigate}
      />
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[var(--app-surface)] text-[var(--app-foreground)] flex">
      {/* 桌面端固定侧边栏 */}
      <aside
        aria-label="桌面主导航"
        className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 z-30 border-r border-[var(--app-border)] bg-[var(--app-card)] shadow-xs"
      >
        {/* 顶部 Brand */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--app-border)] px-5">
          <Link href="/" className="flex items-center gap-2.5" aria-label="Code Navi 首页">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-950 font-mono text-sm font-bold text-white shadow-sm dark:bg-white dark:text-zinc-950">
              CN
            </span>
            <div className="flex flex-col">
              <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-zinc-100">Code Navi</span>
              <span className="text-[10px] text-slate-400 dark:text-zinc-500 font-medium">智教码航平台</span>
            </div>
          </Link>
        </div>

        {/* 导航列表 */}
        <NavigationTree pathname={pathname} />

        {/* 底部 Auth 状态 */}
        <div className="shrink-0 border-t border-[var(--app-border)] p-3">
          <Suspense fallback={null}>
            <AuthNav />
          </Suspense>
        </div>
      </aside>

      {/* 移动端顶部 Header */}
      <div className="flex-1 flex flex-col min-w-0 md:pl-64">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-[var(--app-border)] bg-[var(--app-header)] px-4 backdrop-blur-xl md:hidden">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileDrawerOpen(true)}
              aria-label="打开导航菜单"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--app-border)] bg-[var(--app-card)] text-slate-700 hover:bg-slate-100 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              <Menu className="h-4 w-4" />
            </button>
            <Link href="/" className="flex items-center gap-2" aria-label="Code Navi 首页">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-950 font-mono text-xs font-bold text-white dark:bg-white dark:text-zinc-950">
                CN
              </span>
              <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-zinc-100">Code Navi</span>
            </Link>
          </div>
          <Suspense fallback={null}>
            <AuthNav />
          </Suspense>
        </header>

        {/* 移动端抽屉 (Drawer) */}
        {mobileDrawerOpen && (
          <div
            className="fixed inset-0 z-50 md:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="移动端主导航"
          >
            {/* 遮罩背景 */}
            <div
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity"
              onClick={() => setMobileDrawerOpen(false)}
              aria-hidden="true"
            />
            {/* 抽屉内容 */}
            <div className="fixed inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-[var(--app-card)] shadow-2xl border-r border-[var(--app-border)] animate-in slide-in-from-left duration-200">
              <div className="flex h-14 items-center justify-between border-b border-[var(--app-border)] px-4">
                <Link
                  href="/"
                  onClick={() => setMobileDrawerOpen(false)}
                  className="flex items-center gap-2.5"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-950 font-mono text-xs font-bold text-white dark:bg-white dark:text-zinc-950">
                    CN
                  </span>
                  <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-zinc-100">Code Navi</span>
                </Link>
                <button
                  type="button"
                  onClick={() => setMobileDrawerOpen(false)}
                  aria-label="关闭导航菜单"
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <NavigationTree
                pathname={pathname}
                onNavigate={() => setMobileDrawerOpen(false)}
              />

              <div className="border-t border-[var(--app-border)] p-4">
                <Suspense fallback={null}>
                  <AuthNav />
                </Suspense>
              </div>
            </div>
          </div>
        )}

        {/* Workspace 上下文栏 */}
        <Suspense fallback={null}>
          <WorkspaceContextBar />
        </Suspense>

        {/* 主页面内容 */}
        <main className="flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}

