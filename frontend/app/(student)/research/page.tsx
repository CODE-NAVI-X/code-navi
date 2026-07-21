"use client";

import { Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useFlowStore } from "@/lib/store/flow-store";
import { ArrowLeft, GraduationCap, CheckCircle2, FlaskConical, Loader2 } from "lucide-react";

function ResearchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const knowledgeId = searchParams.get("knowledge_id") || "kp_dhcp_4stage";
  const sessionId = searchParams.get("session_id") || "sess_demo_123";
  const payload = useFlowStore((s) => s.payload);

  const rawPersona = payload?.studentPersona || "academic";
  const displayPersona =
    rawPersona === "academic"
      ? "学术科研路线"
      : rawPersona === "software_coursework"
      ? "软件工程实践"
      : rawPersona;

  return (
    <div className="max-w-2xl w-full bg-zinc-900/90 border border-zinc-800 rounded-3xl p-8 shadow-2xl backdrop-blur-md space-y-6">
      {/* Back button */}
      <button
        type="button"
        onClick={() => router.push("/student/learning")}
        className="inline-flex items-center gap-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
        返回知识点学习
      </button>

      {/* Header */}
      <div className="flex items-center gap-3.5 border-b border-zinc-800/80 pb-5">
        <div className="w-11 h-11 rounded-2xl bg-zinc-800/80 border border-zinc-700/60 flex items-center justify-center text-zinc-300">
          <GraduationCap className="h-5.5 w-5.5" strokeWidth={1.5} />
        </div>
        <div>
          <h1 className="text-lg font-bold text-zinc-100">项目科研助手模块</h1>
          <p className="text-xs text-zinc-400">教学节点闭环接力</p>
        </div>
      </div>

      {/* Success Alert Banner */}
      <div className="bg-gradient-to-r from-emerald-950/40 to-emerald-900/20 border border-emerald-900/60 rounded-2xl p-4 flex items-center gap-3.5">
        <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" strokeWidth={1.5} />
        <div>
          <h3 className="text-xs font-semibold text-emerald-300">上下文数据接力成功 (FlowPayload 契约对齐)</h3>
          <p className="text-[11px] text-emerald-400/80 mt-0.5">已顺利接收上游【知识探索与学术深度解析】模块传递的上下文数据。</p>
        </div>
      </div>

      {/* Data Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-2xl p-4">
          <span className="text-[11px] text-zinc-500 block mb-1">已掌握知识点 ID</span>
          <span className="text-xs font-mono font-semibold text-zinc-200">{payload?.masteredKnowledgePoint.id || knowledgeId}</span>
        </div>

        <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-2xl p-4">
          <span className="text-[11px] text-zinc-500 block mb-1">知识点名称</span>
          <span className="text-xs font-semibold text-zinc-200">{payload?.masteredKnowledgePoint.name || "DHCP 四阶段报文交互"}</span>
        </div>

        <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-2xl p-4">
          <span className="text-[11px] text-zinc-500 block mb-1.5">学员画像</span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-zinc-800 text-zinc-200 border border-zinc-700/80">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            {displayPersona}
          </span>
        </div>

        <div className="bg-zinc-950/70 border border-zinc-800/80 rounded-2xl p-4">
          <span className="text-[11px] text-zinc-500 block mb-1">会话 ID</span>
          <span className="text-xs font-mono text-zinc-300 truncate block">{payload?.sessionId || sessionId}</span>
        </div>
      </div>

      {/* Recommended Topic Section */}
      <div className="bg-zinc-950/50 border border-zinc-800/80 rounded-2xl p-5 space-y-3">
        <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-zinc-400" strokeWidth={1.5} />
          AI 推荐科研与小项目研讨课题
        </h3>
        <div className="bg-zinc-900/90 border border-zinc-800 p-4 rounded-xl text-xs text-zinc-300 leading-relaxed font-medium">
          {payload?.payloadData.recommendedTopic || "基于 DHCP 协议扩展的局域网防御与抓包仿真项目研讨"}
        </div>
      </div>
    </div>
  );
}

export default function ResearchPage() {
  return (
    <main className="min-h-screen bg-zinc-950 bg-grid-pattern text-zinc-100 p-6 sm:p-10 flex flex-col items-center justify-center">
      <Suspense fallback={
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
          页面加载中...
        </div>
      }>
        <ResearchContent />
      </Suspense>
    </main>
  );
}


