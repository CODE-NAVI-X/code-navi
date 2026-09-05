"use client";

import { useEffect, useState } from "react";

import { TechPulseDot } from "@/components/ui/TechPulseDot";
import {
  getResearchProviderStatus,
  type ProviderStatusResponse,
} from "@/lib/api/research";

type LoadState =
  | { state: "loading" }
  | { state: "ready"; status: ProviderStatusResponse }
  | { state: "unavailable" };

/**
 * DESIGN.md §6.6 统一顶栏右侧的 Provider 状态呼吸灯。
 * 只读既有 GET /api/v1/research/provider/status，不新增后端契约；
 * 规则模式或请求失败都如实降级显示，不伪装模型就绪。
 */
export function ProviderStatusIndicator() {
  const [loadState, setLoadState] = useState<LoadState>({ state: "loading" });

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const status = await getResearchProviderStatus();
        if (active) setLoadState({ state: "ready", status });
      } catch {
        if (active) setLoadState({ state: "unavailable" });
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loadState.state === "loading") {
    return (
      <div
        className="hidden items-center gap-2 md:inline-flex"
        aria-label="正在检测 Provider 状态"
      >
        <TechPulseDot tone="neutral" label="Provider 状态检测中" />
        <span className="text-xs font-medium text-[var(--app-muted)]">检测中</span>
      </div>
    );
  }

  if (loadState.state === "unavailable") {
    return (
      <div className="hidden items-center gap-2 md:inline-flex">
        <TechPulseDot tone="red" label="Provider 状态不可用" />
        <span className="text-xs font-medium text-[var(--app-muted)]">服务不可用</span>
      </div>
    );
  }

  const { status } = loadState;
  const modelReady = status.mode === "model" && status.configured;
  return (
    <div
      className="hidden items-center gap-2 md:inline-flex"
      title={`Provider：${status.provider}${status.model ? ` · ${status.model}` : ""}`}
    >
      <TechPulseDot
        tone={modelReady ? "emerald" : "amber"}
        label={modelReady ? "Provider 就绪" : "Provider 规则模式"}
      />
      <span className="font-mono text-xs tracking-wider text-[var(--app-muted)]">
        {modelReady ? "LLM Ready" : "规则模式"}
      </span>
    </div>
  );
}
