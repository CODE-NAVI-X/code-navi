"use client";

import { Suspense, useEffect, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getLearningSessionId } from "@/lib/api/learning";

/**
 * Lightweight session guard for every page under the `(student)` route group.
 *
 * There is no login wall yet — the project's "session" is the anonymous,
 * localStorage-backed learning session id. What this layout guarantees is
 * structural isolation:
 *
 * 1. the browser's session id is read-or-minted synchronously (localStorage),
 *    so it is confirmed during render — no "ready" state gate is needed, and
 * 2. a `session_id` passed in the URL that disagrees with the browser's own id
 *    is rewritten to the real id, so directly typing a URL can never smuggle
 *    another session's context in.
 */
function SessionGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const sessionId = getLearningSessionId();

  useEffect(() => {
    const urlSessionId = searchParams?.get("session_id");
    if (urlSessionId && urlSessionId !== sessionId) {
      const params = new URLSearchParams(searchParams.toString());
      params.set("session_id", sessionId);
      router.replace(
        `${window.location.pathname}?${params.toString()}${window.location.hash}`,
      );
    }
  }, [router, searchParams, sessionId]);

  return <>{children}</>;
}

export default function StudentLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <Suspense fallback={null}>
      <SessionGuard>{children}</SessionGuard>
    </Suspense>
  );
}
