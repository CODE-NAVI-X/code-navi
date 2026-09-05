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
  FolderGit2,
  Menu,
  Microscope,
  Sparkles,
  Telescope,
  User,
  Users,
  X,
} from "lucide-react";
import { WorkspaceContextBar } from "@/components/WorkspaceContextBar";
import { AuthNav } from "@/components/AuthNav";
import { ProviderStatusIndicator } from "@/components/ProviderStatusIndicator";

interface NavItem {
  href: string;
  label: string;
  icon: typeof BriefcaseBusiness;
  exact?: boolean;
  matchPrefix?: string;
  isWorkbench?: boolean;
}

// D5 Q1 拍板：学习闭环五入口，/learning/projects 为本次新增侧边栏入口。
const learningSubItems: NavItem[] = [
  { href: "/learning", label: "理解学习", icon: BookOpen, exact: true },
  { href: "/learning/practice", label: "动手实践", icon: Code2, matchPrefix: "/learning/practice" },
  { href: "/learning/projects", label: "项目代码", icon: FolderGit2, matchPrefix: "/learning/projects" },
  { href: "/learning/portrait", label: "知识复盘", icon: BarChart3, matchPrefix: "/learning/portrait" },
  { href: "/learning/notebook", label: "学习笔记", icon: ClipboardList, matchPrefix: "/learning/notebook" },
];

const managementItems: NavItem[] = [
  { href: "/classes", label: "班级成员", icon: Users, matchPrefix: "/classes" },
  { href: "/account", label: "账户设置", icon: User, matchPrefix: "/account" },
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

function isResearchActive(pathname: string): boolean {
  return pathname === "/research" || pathname.startsWith("/research/");
}

function NavLink({
  item,
  pathname,
  onNavigate,
  compact = false,
  className = "",
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
  compact?: boolean;
  className?: string;
}) {
  const active = isItemActive(item, pathname);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-3 rounded-control font-semibold transition ${
        compact ? "px-3 py-2 text-xs" : "px-3 py-2.5 text-sm"
      } ${className} ${
        active
          ? "bg-slate-950 text-white shadow-sm dark:bg-white dark:text-zinc-950"
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white"
      }`}
    >
      <Icon className={compact ? "h-3.5 w-3.5 shrink-0" : "h-4 w-4 shrink-0"} strokeWidth={1.8} />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

function NavGroupTitle({
  title,
  icon: Icon,
  active,
}: {
  title: string;
  icon: typeof Sparkles;
  active?: boolean;
}) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-xs font-bold tracking-wider text-slate-500 uppercase dark:text-zinc-400">
      <div className="flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 text-blue-500" strokeWidth={1.8} />
        <span>{title}</span>
      </div>
      {active && <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />}
    </div>
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
    <nav aria-label="侧边栏主导航" className="flex flex-1 flex-col gap-1.5 overflow-y-auto px-3 py-4">
      {/* 1. 工作台（终审裁决：必须保留为导航树首项） */}
      <NavLink
        item={{ href: "/", label: "工作台", icon: BriefcaseBusiness, isWorkbench: true }}
        pathname={pathname}
        onNavigate={onNavigate}
      />

      {/* 2. 学习闭环 */}
      <div className="mt-3">
        <NavGroupTitle title="学习闭环" icon={Sparkles} active={learningActive} />
        <div className="mt-1 flex flex-col gap-1 pl-2 border-l-2 border-slate-200/80 ml-2 dark:border-zinc-800">
          {learningSubItems.map((subItem) => (
            <NavLink
              key={subItem.href}
              item={subItem}
              pathname={pathname}
              onNavigate={onNavigate}
              compact
            />
          ))}
        </div>
      </div>

      {/* 3. 科研专区 */}
      <div className="mt-3">
        <NavGroupTitle title="科研专区" icon={Telescope} active={isResearchActive(pathname)} />
        <div className="mt-1 flex flex-col gap-1 pl-2 border-l-2 border-slate-200/80 ml-2 dark:border-zinc-800">
          <NavLink
            item={{ href: "/research", label: "科研引导", icon: Microscope, matchPrefix: "/research" }}
            pathname={pathname}
            onNavigate={onNavigate}
            compact
          />
        </div>
      </div>

      {/* 4. 组织管理（D5 Q1 拍板：视觉降级，下沉底部次级分区） */}
      <div className="mt-auto pt-3">
        <div className="border-t border-[var(--app-border)] pt-3">
          <div className="flex items-center px-3 py-1.5 text-xs font-bold tracking-wider text-slate-500 uppercase dark:text-zinc-400">
            <span>组织管理</span>
          </div>
          <div className="mt-1 flex flex-col gap-1">
            {managementItems.map((subItem) => (
              <NavLink
                key={subItem.href}
                item={subItem}
                pathname={pathname}
                onNavigate={onNavigate}
                compact
                className="text-slate-500 dark:text-zinc-400"
              />
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-[var(--app-surface)] text-[var(--app-foreground)]">
      {/* 统一顶栏（D5 Q3 拍板）：管「我在哪、我是谁」，零路由项 */}
      <header className="sticky top-0 z-40 flex h-12 shrink-0 items-center gap-2 border-b border-[var(--app-border)] bg-[var(--app-header)] px-3 backdrop-blur-xl md:h-16 md:gap-3 md:px-5">
        <button
          type="button"
          onClick={() => setMobileDrawerOpen(true)}
          aria-label="打开导航菜单"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border border-[var(--app-border)] bg-[var(--app-card)] text-slate-700 hover:bg-slate-100 dark:text-zinc-200 dark:hover:bg-zinc-800 md:hidden"
        >
          <Menu className="h-4 w-4" />
        </button>

        <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="Code Navi 首页">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-control bg-slate-950 font-mono text-xs font-bold text-white shadow-sm dark:bg-white dark:text-zinc-950 md:h-8 md:w-8">
            CN
          </span>
          <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-zinc-100">
            Code Navi
          </span>
        </Link>

        <span
          className="mx-1 hidden h-6 w-px bg-[var(--app-border)] md:block"
          aria-hidden="true"
        />

        {/* Workspace / Task 上下文面包屑（原独立上下文条内聚于此） */}
        <Suspense fallback={null}>
          <WorkspaceContextBar />
        </Suspense>

        <div className="ml-auto flex shrink-0 items-center gap-2 md:gap-3">
          <ProviderStatusIndicator />
          <Suspense fallback={null}>
            <AuthNav />
          </Suspense>
        </div>
      </header>

      <div className="flex min-w-0 flex-1">
        {/* 桌面侧边栏：管「去哪里」 */}
        <aside
          aria-label="桌面主导航"
          className="fixed left-0 top-12 bottom-0 z-30 hidden w-64 flex-col border-r border-[var(--app-border)] bg-[var(--app-card)] shadow-xs md:flex"
        >
          <NavigationTree pathname={pathname} />
        </aside>

        <main className="min-w-0 flex-1 md:pl-64">{children}</main>
      </div>

      {/* 移动端抽屉 (Drawer)：390×844 降级，遮罩点击关闭 */}
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
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--app-border)] px-4">
              <Link
                href="/"
                onClick={() => setMobileDrawerOpen(false)}
                className="flex items-center gap-2.5"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-control bg-slate-950 font-mono text-xs font-bold text-white dark:bg-white dark:text-zinc-950">
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
          </div>
        </div>
      )}
    </div>
  );
}
