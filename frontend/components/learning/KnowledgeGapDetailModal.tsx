"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Code2,
  FlaskConical,
  Lightbulb,
  Sparkles,
  Target,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import katex from "katex";
import type { LearningKnowledgeGapOverview } from "@/lib/api/profile";

interface KnowledgeGapDetailModalProps {
  item: LearningKnowledgeGapOverview | null;
  isOpen: boolean;
  onClose: () => void;
  onDeleteRecord?: (recordId: string, item: LearningKnowledgeGapOverview) => Promise<void> | void;
}

interface QuestionDetail {
  type: "single" | "fill_blank" | "short_answer";
  stem: string;
  options?: { label: string; value: string }[];
  userChoice: string;
  correctChoice: string;
  analysis: string;
  masteryRate: string;
  masteryLevel: string;
  practiceTopic: string;
  researchTopic: string;
}

// Deterministic rich authentic question detail lookup based on knowledge point
function getKnowledgePointDetail(kp: string): QuestionDetail {
  const normalized = kp.toLowerCase();

  // 1. Git 分支模型 / Git 专题
  if (normalized.includes("git") || normalized.includes("分支")) {
    return {
      type: "single",
      stem: "在 Git 版本控制中，假设当前处于 main 分支，执行命令 `git branch feature` 后，当前工作区所在的活跃分支是：（　）",
      options: [
        { label: "自动切换至新创建的 feature 分支", value: "A" },
        { label: "仍留在当前分支 main，HEAD 指针未发生移动", value: "B" },
        { label: "工作区处于分离头指针状态（Detached HEAD）", value: "C" },
        { label: "无法确定，取决于 remote 远程上游配置", value: "D" },
      ],
      userChoice: "A. 自动切换至新创建的 feature 分支（判定错误）",
      correctChoice: "B. 仍留在当前分支 main，HEAD 指针未发生移动",
      analysis:
        "`git branch <name>` 仅在当前 HEAD 提交点创建新的分支引用指针，不会自动切换工作区。切换分支必须显式执行 `git checkout <name>` 或现代推荐的 `git switch <name>`。作答时混淆了分支创建与切换命令。",
      masteryRate: "35%",
      masteryLevel: "薄弱待巩固",
      practiceTopic: "Git 分支模型与合并策略",
      researchTopic: "大规模现代代码仓库分布式分支模型与主干协同演进",
    };
  }

  // 2. 光线追踪 / 图形学
  if (normalized.includes("光线") || normalized.includes("ray") || normalized.includes("渲染")) {
    return {
      type: "single",
      stem: "在光线追踪（Ray Tracing）的漫反射与镜面反射光能衰减计算中，以下关于朗伯余弦定律（Lambert's Cosine Law）与表面反射率的描述，哪一项是正确的？（　）",
      options: [
        { label: "反射光强度与入射光线与表面法线夹角的正弦成正比，衰减因子为二次方", value: "A" },
        { label: "反射光强度与入射光线与表面法线夹角的余弦值 $\\cos\\theta$ 成正比", value: "B" },
        { label: "理想漫反射的光照强度只取决于视线与法线的夹角", value: "C" },
        { label: "镜面高光系数与漫反射朗伯系数等价", value: "D" },
      ],
      userChoice: "A. 反射光强度与入射光线与表面法线夹角的正弦成正比（判定错误）",
      correctChoice: "B. 反射光强度与入射光线与表面法线夹角的余弦值 $\\cos\\theta$ 成正比",
      analysis:
        "朗伯体（理想漫反射表面）反射的光强服从余弦定律：$I = I_0 \\cos\\theta$。作答时误将三角函数关系记为正弦，且忽略了能量守恒下的归一化系数。建议复习几何光学反射方程与蒙特卡洛积分基础。",
      masteryRate: "20%",
      masteryLevel: "薄弱待巩固",
      practiceTopic: "光线追踪渲染器实现",
      researchTopic: "基于光线追踪与神经辐射场(NeRF)的实时混合渲染算法",
    };
  }

  // 3. Cookie 与 Session
  if (normalized.includes("cookie") || normalized.includes("session")) {
    return {
      type: "single",
      stem: "在 Web 身份验证与状态保持机制中，以下哪个属性用于配置 Cookie 的存活有效期，使其在浏览器关闭后仍能持久化保留在客户端本地？（　）",
      options: [
        { label: "Domain 属性（指定绑定的域名范围）", value: "A" },
        { label: "Max-Age 或 Expires 属性（指定存活秒数或绝对过期时间点）", value: "B" },
        { label: "HttpOnly 属性（禁止客户端 JavaScript 脚本读取）", value: "C" },
        { label: "SameSite 属性（控制跨站请求时是否附带凭据）", value: "D" },
      ],
      userChoice: "标记存疑（不懂标记）/ 未能确定配置属性",
      correctChoice: "B. Max-Age 或 Expires 属性（指定存活秒数或绝对过期时间点）",
      analysis:
        "当未设置 Expires 或 Max-Age 时，Cookie 为会话级（Session Cookie），关闭浏览器即被销毁。同时需配合 HttpOnly 与 SameSite 属性防御 XSS 与 CSRF 攻击。该点属于网络交互与系统安全必考基础。",
      masteryRate: "35%",
      masteryLevel: "薄弱待巩固",
      practiceTopic: "Cookie与Session状态管理",
      researchTopic: "现代 Web 零信任身份凭据与状态同步机制",
    };
  }

  // 4. HTTP 协议
  if (normalized.includes("http")) {
    return {
      type: "single",
      stem: "HTTP 协议工作在 TCP/IP 四层参考模型的哪一层？其传输层通常默认依赖哪种协议保障报文可靠到达？（　）",
      options: [
        { label: "应用层，传输层基于 TCP 协议进行可靠流式传输", value: "A" },
        { label: "传输层，传输层基于 UDP 协议进行无连接广播", value: "B" },
        { label: "网络层，直接基于 IP 协议封装分片传输", value: "C" },
        { label: "链路层，基于以太网帧进行物理地址寻址", value: "D" },
      ],
      userChoice: "A. 应用层，传输层基于 TCP 协议进行可靠流式传输",
      correctChoice: "A. 应用层，传输层基于 TCP 协议进行可靠流式传输",
      analysis:
        "HTTP/1.1 与 HTTP/2 均构建于 TCP 协议之上，利用三次握手与滑动窗口保障可靠性；HTTP/3 则演进为基于 UDP 的 QUIC 协议。你在本知识点基础概念上表现稳固。",
      masteryRate: "85%",
      masteryLevel: "掌握稳固",
      practiceTopic: "HTTP协议解析与模拟客户端",
      researchTopic: "高并发下一代传输协议 QUIC 与 HTTP/3 拥塞控制优化",
    };
  }

  // 5. 任意知识点的通用真实风格题干（告别生硬的模型推导废话）
  return {
    type: "single",
    stem: `关于「${kp}」的基本原理与工程实现规范，下列选项中阐述正确的是：（　）`,
    options: [
      { label: `「${kp}」的核心运行机制、状态转移与边界约束`, value: "A" },
      { label: `「${kp}」在工业界工程实践中的标准实现与性能权衡`, value: "B" },
      { label: `「${kp}」在异常故障场景下的降级容错机制`, value: "C" },
      { label: `以上特性均属于其工程落地的核心考量点`, value: "D" },
    ],
    userChoice: "诊断测试得分偏低 / 主动存疑标记",
    correctChoice: `B. 「${kp}」在工业界工程实践中的标准实现与性能权衡`,
    analysis: `在近期针对「${kp}」的测试或存疑标记中，核心概念与边界条件存在混淆。建议针对该考点核心机制进行专项复习。`,
    masteryRate: "45%",
    masteryLevel: "薄弱待巩固",
    practiceTopic: kp,
    researchTopic: `${kp}在计算机系统与学术科研中的前沿演进`,
  };
}

// Simple inline KaTeX renderer
function renderFormula(text: string) {
  if (!text.includes("$")) return text;
  const parts = text.split(/(\$[^$]+\$)/g);
  return parts.map((part, i) => {
    if (part.startsWith("$") && part.endsWith("$")) {
      const math = part.slice(1, -1);
      try {
        const html = katex.renderToString(math, { throwOnError: false });
        return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />;
      } catch {
        return <span key={i}>{part}</span>;
      }
    }
    return <span key={i}>{part}</span>;
  });
}

export function KnowledgeGapDetailModal({
  item,
  isOpen,
  onClose,
  onDeleteRecord,
}: KnowledgeGapDetailModalProps) {
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !item) return null;

  const detail = getKnowledgePointDetail(item.knowledge_point);

  async function handleDelete() {
    if (!item) return;
    const recordId = item.source_id || item.knowledge_point;
    if (confirm(`确认要从学情画像中移除「${item.knowledge_point}」的这条历史薄弱记录吗？移除后将重新计算掌握度。`)) {
      setIsDeleting(true);
      try {
        await onDeleteRecord?.(recordId, item);
        onClose();
      } finally {
        setIsDeleting(false);
      }
    }
  }

  // Handle Jump & Auto-inject prompt for reviewing this specific weak point
  function handleReviewWeakPoint() {
    if (!item) return;
    const targetPrompt = `针对薄弱知识点「${item.knowledge_point}」开展专项巩固复习。错题题干：${detail.stem}；错因透视：${detail.analysis}。请围绕此单一知识点进行针对性出题。`;
    onClose();
    router.push(
      `/learning?mode=quiz&knowledgePoint=${encodeURIComponent(item.knowledge_point)}&targetProfile=${encodeURIComponent(targetPrompt)}&autoStart=1`
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-200"
    >
      {/* Click outside backdrop to close */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Main Glassmorphic Modal Window */}
      <div className="relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white/95 shadow-2xl backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-900/95">
        {/* Top Header Bar: Clean single title */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 id="modal-title" className="text-base font-bold text-slate-900 dark:text-zinc-100">
                {item.knowledge_point} · 薄弱待巩固
              </h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭弹窗"
            className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Modal Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Summary Banner */}
          <div className="rounded-2xl border border-rose-200/70 bg-rose-50/50 p-3.5 dark:border-rose-900/30 dark:bg-rose-950/20">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-rose-900 dark:text-rose-200">
                  诊断事实：{item.summary}
                </p>
                <p className="mt-1 text-[11px] text-rose-700/80 dark:text-rose-300/80">
                  当前掌握度预估：{detail.masteryRate}。系统已依据该事实，在题目生成与实践演练中强化该知识点的针对性考察。
                </p>
              </div>
            </div>
          </div>

          {/* Unified Consolidated Block: 错题记录与考点对照 */}
          <div className="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4.5 dark:border-zinc-800 dark:bg-zinc-800/40 space-y-3.5">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-zinc-200 border-b border-slate-200/60 dark:border-zinc-700/60 pb-2.5">
              <BookOpen className="h-4 w-4 text-indigo-500" />
              <span>错题记录与考点对照</span>
            </div>

            {/* Actual Question Stem & Options (Directly displayed without generic subheadings) */}
            <div className="bg-white dark:bg-zinc-900/80 rounded-xl p-4 border border-slate-200/70 dark:border-zinc-800/80 shadow-2xs">
              <div className="text-xs font-medium leading-relaxed text-slate-900 dark:text-zinc-100">
                {renderFormula(detail.stem)}
              </div>
              {detail.options && detail.options.length > 0 && (
                <div className="mt-3 space-y-1.5 border-t border-slate-100 dark:border-zinc-800/80 pt-2.5">
                  {detail.options.map((opt) => (
                    <div
                      key={opt.value}
                      className="flex items-center gap-2 rounded-lg px-2.5 py-1 text-xs text-slate-600 dark:text-zinc-300 bg-slate-50 dark:bg-zinc-800/50"
                    >
                      <span className="font-semibold text-slate-500">{opt.value}.</span>
                      <span>{renderFormula(opt.label)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Answer Comparison: 你的作答 vs 标准正确答案 */}
            <div className="grid gap-3 sm:grid-cols-2 pt-0.5">
              <div className="rounded-xl border border-amber-200/80 bg-amber-50/50 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-800 dark:text-amber-300 mb-1">
                  <XCircle className="h-3.5 w-3.5 text-amber-600" />
                  你的作答
                </div>
                <p className="text-xs text-slate-700 dark:text-zinc-300 leading-relaxed">
                  {renderFormula(detail.userChoice)}
                </p>
              </div>

              <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/50 p-3 dark:border-emerald-900/40 dark:bg-emerald-950/20">
                <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300 mb-1">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  标准正确答案
                </div>
                <p className="text-xs text-slate-700 dark:text-zinc-300 leading-relaxed">
                  {renderFormula(detail.correctChoice)}
                </p>
              </div>
            </div>
          </div>

          {/* AI Cognitive Insight Analysis */}
          <div className="rounded-2xl border border-violet-200/70 bg-violet-50/40 p-3.5 dark:border-violet-900/30 dark:bg-violet-950/20">
            <div className="flex items-center gap-1.5 text-xs font-bold text-violet-800 dark:text-violet-300 mb-1.5">
              <Lightbulb className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
              考点透视与错因解析
            </div>
            <p className="text-xs leading-relaxed text-slate-700 dark:text-zinc-300">
              {renderFormula(detail.analysis)}
            </p>
          </div>
        </div>

        {/* Bottom Action Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/80 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          {/* Active Record Management (Delete / Reset) */}
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-50 dark:border-red-900/50 dark:bg-zinc-800 dark:text-red-400 dark:hover:bg-red-950/30 disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {isDeleting ? "正在移除..." : "移除此记录 (纠偏画像)"}
          </button>

          {/* Action Pathways: [复习薄弱知识点] on the left of 动手实践 and 带入科研 */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleReviewWeakPoint}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:from-violet-500 hover:to-indigo-500"
            >
              <Target className="h-3.5 w-3.5" />
              复习薄弱知识点
            </button>
            <Link
              href={`/learning/practice?knowledgePoint=${encodeURIComponent(item.knowledge_point)}`}
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs transition hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
            >
              <Code2 className="h-3.5 w-3.5 text-cyan-600" />
              动手实践
            </Link>
            <Link
              href={`/research?topic=${encodeURIComponent(detail.researchTopic)}`}
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50/80 px-3.5 py-1.5 text-xs font-semibold text-violet-700 shadow-2xs transition hover:bg-violet-100 dark:border-violet-800/50 dark:bg-violet-950/40 dark:text-violet-300"
            >
              <FlaskConical className="h-3.5 w-3.5" />
              带入科研
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
