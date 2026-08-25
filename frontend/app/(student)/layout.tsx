"use client";

import { Suspense, useEffect, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { getLearningSessionId } from "@/lib/api/learning";
import { useAuth } from "@/lib/context/auth-context";

function SessionGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { mode, loading } = useAuth();

  const sessionId = getLearningSessionId();

  // Rewrite session_id in URL if it conflicts with browser session
  useEffect(() => {
    const urlSessionId = searchParams?.get("session_id");
    if (urlSessionId && urlSessionId !== sessionId) {
      const params = new URLSearchParams(searchParams.toString());
      params.set("session_id", sessionId);
      router.replace(
        `${pathname}?${params.toString()}${window.location.hash}`,
      );
    }
  }, [router, pathname, searchParams, sessionId]);

  // Hard Login Wall check
  useEffect(() => {
    if (!loading && mode !== "authenticated") {
      const query = searchParams?.toString();
      const currentUrl = `${pathname}${query ? `?${query}` : ""}`;
      router.replace(`/login?next=${encodeURIComponent(currentUrl)}`);
    }
  }, [loading, mode, pathname, searchParams, router]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900 dark:border-zinc-700 dark:border-t-zinc-100" />
          <p className="text-xs text-slate-500 dark:text-zinc-400">正在验证登录状态...</p>
        </div>
      </div>
    );
  }

  if (mode !== "authenticated") {
    return (
      <div className="flex-1 flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-2">
          <p className="text-xs text-slate-500 dark:text-zinc-400">正在跳转至登录页面...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export default function StudentLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <AppShell>
      <Suspense fallback={null}>
        <SessionGuard>{children}</SessionGuard>
      </Suspense>
    </AppShell>
  );
}

