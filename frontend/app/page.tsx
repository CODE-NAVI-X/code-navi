"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  ChevronDown,
  Code2,
  Compass,
  Microscope,
  Sparkles,
  Zap,
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  getLocalProfileId,
  listRecentTasks,
  type WorkspaceTask,
} from "@/lib/api/workspaces";
import {
  fetchPortraitsOverview,
  type PortraitsOverviewResponse,
} from "@/lib/api/profile";
import { getPersistedFlowPayload, type FlowPayload } from "@/lib/store/flow-store";
import { getOrCreateLearnerId } from "@/lib/learner";
import { useAuth } from "@/lib/context/auth-context";

type OverviewState = "loading" | "ready" | "error";

// ── 4大能力晶体卡片（Uiverse Galaxy 极简黑曜石玻璃质感） ─────────────────────────
const capabilityCards = [
  {
    index: "01",
    title: "概念理解",
    description: "原理深度解析 · 概念问答",
    href: "/learning",
    cta: "开始探索",
    icon: BookOpen,
    badge: null,
  },
  {
    index: "02",
    title: "动手实践",
    description: "实操填空判题 · 代码验证",
    href: "/learning/practice",
    cta: "进入实践",
    icon: Code2,
    badge: null,
  },
  {
    index: "03",
    title: "技能复盘",
    description: "星轨能力雷达 · 缺口透视",
    href: "/learning/portrait",
    cta: "查看画像",
    icon: BarChart3,
    badge: null,
  },
  {
    index: "04",
    title: "科研引导",
    description: "学术论文精读 · 研讨跃迁",
    href: "/research",
    cta: "进入科研",
    icon: Microscope,
    badge: "APEX",
  },
];

// ── 逐字错峰浮入组件（Splitting Text into Staggered Characters） ─────────────
function StaggerText({
  text,
  active,
  baseDelay = 0,
  charInterval = 42,
  className = "",
}: {
  text: string;
  active: boolean;
  baseDelay?: number;
  charInterval?: number;
  className?: string;
}) {
  const chars = Array.from(text);
  return (
    <span className={className}>
      {chars.map((char, index) => (
        <span
          key={`${char}-${index}`}
          className={active ? "animate-stagger-char" : "opacity-0"}
          style={active ? { animationDelay: `${baseDelay + index * charInterval}ms` } : undefined}
        >
          {char === " " ? "\u00A0" : char}
        </span>
      ))}
    </span>
  );
}

export default function HomePage() {
  const router = useRouter();
  const { mode, loading: authLoading } = useAuth();
  const [recentTasks, setRecentTasks] = useState<WorkspaceTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [flowPayload, setFlowPayload] = useState<FlowPayload | null>(null);
  const [overview, setOverview] = useState<PortraitsOverviewResponse | null>(null);
  const [overviewState, setOverviewState] = useState<OverviewState>("loading");

  // ── 视差滚轮与双幕吸附控制器 ──────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null);
  const scene1Ref = useRef<HTMLDivElement>(null);
  const scene2Ref = useRef<HTMLDivElement>(null);
  const [activeScene, setActiveScene] = useState<0 | 1>(0);

  // ── 鼠标平滑视差微动 (Parallax on Mouse Move) ─────────────────────────────
  const [mouseOffset, setMouseOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    let reqId: number;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    const onMouseMove = (e: MouseEvent) => {
      targetX = (e.clientX / window.innerWidth - 0.5) * 2;
      targetY = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    const updateParallax = () => {
      currentX += (targetX - currentX) * 0.07;
      currentY += (targetY - currentY) * 0.07;
      setMouseOffset({ x: currentX, y: currentY });
      reqId = requestAnimationFrame(updateParallax);
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    reqId = requestAnimationFrame(updateParallax);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      cancelAnimationFrame(reqId);
    };
  }, []);

  // ── 认证与数据恢复 ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!authLoading && mode !== "authenticated") {
      router.replace("/login");
    }
  }, [authLoading, mode, router]);

  const load = useCallback(async () => {
    if (mode !== "authenticated") return;
    setLoading(true);
    setError(null);
    try {
      const tasks = await listRecentTasks();
      setRecentTasks(tasks);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    if (mode === "authenticated") {
      const timeoutId = window.setTimeout(() => {
        void load();
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }
  }, [load, mode]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setFlowPayload(getPersistedFlowPayload());
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, []);

  useEffect(() => {
    if (mode !== "authenticated") return;
    let active = true;
    const timeoutId = window.setTimeout(() => {
      setOverviewState("loading");
      void (async () => {
        try {
          const response = await fetchPortraitsOverview(getOrCreateLearnerId(), {
            localProfileId: getLocalProfileId(),
            conversationLimit: 5,
          });
          if (active) {
            setOverview(response);
            setOverviewState("ready");
          }
        } catch {
          if (active) setOverviewState("error");
        }
      })();
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [mode]);

  const practiceTopic = flowPayload?.knowledgePoint || null;
  const latestTask = recentTasks[0] || null;
  const latestConversation = overview?.conversations?.[0] || null;
  const hasResumeEntry = Boolean(practiceTopic || latestTask || latestConversation);

  // ── 滚屏与双场景定位交互 ─────────────────────────────────────────────────
  const scrollToScene2 = useCallback(() => {
    if (scene2Ref.current) {
      scene2Ref.current.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  const scrollToScene1 = useCallback(() => {
    if (scene1Ref.current) {
      scene1Ref.current.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  // 监听当前进入视野的场景
  useEffect(() => {
    const s2 = scene2Ref.current;
    if (!s2) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && entry.intersectionRatio >= 0.3) {
          setActiveScene(1);
        } else if (!entry.isIntersecting || entry.intersectionRatio < 0.2) {
          setActiveScene(0);
        }
      },
      { threshold: [0.1, 0.3, 0.6] },
    );

    observer.observe(s2);
    return () => observer.disconnect();
  }, []);

  // 鼠标滚轮双向精准吸附（绝不卡在中间）
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let isSnapping = false;
    let snapTimeout: number | null = null;

    const handleWheel = (e: WheelEvent) => {
      if (isSnapping) return;

      const scrollTop = container.scrollTop;
      const threshold = 80;

      // 在场景一往下滑动
      if (scrollTop < threshold && e.deltaY > 16) {
        e.preventDefault();
        isSnapping = true;
        scrollToScene2();
        snapTimeout = window.setTimeout(() => {
          isSnapping = false;
        }, 650);
      }
      // 在场景二顶部往上滑动
      else if (scrollTop > threshold && scrollTop <= window.innerHeight * 0.9 && e.deltaY < -16) {
        e.preventDefault();
        isSnapping = true;
        scrollToScene1();
        snapTimeout = window.setTimeout(() => {
          isSnapping = false;
        }, 650);
      }
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      container.removeEventListener("wheel", handleWheel);
      if (snapTimeout) window.clearTimeout(snapTimeout);
    };
  }, [scrollToScene1, scrollToScene2]);

  return (
    <AppShell>
      {/* ── 视差宇宙画布容器 ────────────────────────────────────────────── */}
      <div className="workbench-map-root relative">
        {/* 全景背景地图图层（受鼠标微动视差平滑驱动） */}
        <div
          aria-hidden="true"
          className="workbench-map-bg"
          style={{
            backgroundImage: "url('/images/backgrounds/learning-observatory-hero.webp')",
            transform: `translate3d(${mouseOffset.x * -22}px, ${mouseOffset.y * -16}px, 0) scale(1.08)`,
            transition: "transform 100ms cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        />
        {/* 深邃星空柔光遮罩 */}
        <div aria-hidden="true" className="workbench-map-scrim" />

        {/* ── 双幕吸附式主容器 (Snap Container) ─────────────────────────── */}
        <div
          ref={containerRef}
          className="workbench-snap-container relative z-10"
        >
          {/* ════════════════════════════════════════════════════════════════
              第一幕：纯粹艺术底图 + 悬浮 Code Navi 徽标（Initial Art Cover）
             ════════════════════════════════════════════════════════════════ */}
          <section
            ref={scene1Ref}
            className="workbench-snap-section relative flex min-h-full w-full flex-col items-center justify-between px-4 py-8 sm:py-12"
          >
            {/* 顶部对齐留白 */}
            <div className="pt-2" aria-hidden="true" />

            {/* 中间核心 LOGO 与品牌图腾（受鼠标视差微动反向浮动） */}
            <div
              className="my-auto flex flex-col items-center justify-center text-center transition-transform duration-100 ease-out"
              style={{
                transform: `translate3d(${mouseOffset.x * 12}px, ${mouseOffset.y * 10}px, 0)`,
              }}
            >
              {/* 空间晶体徽标 */}
              <div className="relative mb-6 flex h-24 w-24 sm:h-28 sm:w-28 items-center justify-center">
                <div className="absolute inset-0 rounded-3xl bg-gradient-to-tr from-indigo-500/35 via-purple-500/40 to-cyan-400/25 blur-xl animate-pulse" />
                <div className="relative flex h-full w-full items-center justify-center rounded-3xl border border-white/30 bg-white/10 backdrop-blur-2xl shadow-2xl shadow-purple-950/60 ring-1 ring-white/20">
                  <Compass className="h-12 w-12 sm:h-14 sm:w-14 text-white drop-shadow-[0_0_15px_rgba(167,139,250,0.85)] animate-[spin_32s_linear_infinite]" strokeWidth={1.5} />
                </div>
              </div>

              {/* 品牌大标题 */}
              <h1 className="text-5xl sm:text-7xl lg:text-8xl font-black tracking-tight text-white drop-shadow-lg">
                <span className="bg-gradient-to-r from-white via-indigo-100 to-purple-200 bg-clip-text text-transparent">
                  CODE NAVI
                </span>
              </h1>

              <p className="mt-4 max-w-xl text-base sm:text-lg text-purple-200/85 leading-relaxed drop-shadow-xs font-medium">
                面向理解、实践与科研探索的下一代计算机智能研学工作台
              </p>

              <div className="mt-8 flex items-center gap-4">
                <button
                  type="button"
                  onClick={scrollToScene2}
                  className="inline-flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-full bg-gradient-to-r from-white via-purple-50 to-indigo-100 px-7 py-3 text-sm font-bold text-indigo-950 shadow-xl shadow-purple-950/50 transition hover:bg-white hover:-translate-y-0.5 hover:shadow-2xl active:scale-95"
                >
                  <span>开启全景探索</span>
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* 底部吸附下滑提示器 */}
            <div className="pb-4">
              <button
                type="button"
                onClick={scrollToScene2}
                className="group flex flex-col items-center gap-2 text-xs font-semibold text-purple-200/70 hover:text-white transition cursor-pointer"
                aria-label="向下滚动进入工作台"
              >
                <span className="tracking-widest uppercase text-[11px] font-mono group-hover:text-purple-200 transition-colors">
                  向下滚动 · 进入工作台
                </span>
                <div className="flex h-8 w-5 items-start justify-center rounded-full border-2 border-white/20 p-1 group-hover:border-white/50 transition-colors">
                  <div className="h-2 w-1 rounded-full bg-white/70 animate-bounce" />
                </div>
                <ChevronDown className="h-4 w-4 text-purple-300/80 animate-bounce group-hover:text-white" />
              </button>
            </div>
          </section>

          {/* ════════════════════════════════════════════════════════════════
              第二幕：互动工作台（Interactive Workbench）
             ════════════════════════════════════════════════════════════════ */}
          <section
            ref={scene2Ref}
            className="workbench-snap-section relative min-h-full w-full px-4 pt-8 pb-20 sm:px-6 sm:pt-10 sm:pb-24 lg:px-12"
          >
            <div className="mx-auto max-w-6xl">
              {/* ── 核心品牌标语：逐字错峰浮入 ─────────────────────────── */}
              <div className="max-w-3xl pt-2 sm:pt-4">
                <h2
                  id="workbench-hero-title"
                  className="text-3xl font-black tracking-tight text-white sm:text-5xl lg:text-6xl leading-[1.15]"
                >
                  <div className="block">
                    <StaggerText
                      text="从一个问题出发，"
                      active={activeScene === 1}
                      baseDelay={100}
                      charInterval={45}
                      className="text-white"
                    />
                  </div>
                  <div className="mt-2 block">
                    <StaggerText
                      text="抵达可以实践的理解"
                      active={activeScene === 1}
                      baseDelay={450}
                      charInterval={45}
                      className="text-white drop-shadow-[0_2px_14px_rgba(255,255,255,0.3)]"
                    />
                  </div>
                </h2>

                <p
                  className={`mt-4 text-base sm:text-lg text-purple-100/85 leading-relaxed drop-shadow-xs max-w-2xl ${
                    activeScene === 1 ? "animate-fade-up" : "opacity-0"
                  }`}
                  style={{ animationDelay: "850ms" }}
                >
                  输入概念、问题或材料片段，沿着理解、诊断、实践与复盘，形成属于你的学习路径。
                </p>

                {/* 3大 CTA 按钮：错峰逐个呈现 */}
                <div className="mt-7 flex flex-wrap items-center gap-3.5">
                  <button
                    type="button"
                    onClick={() => router.push("/learning")}
                    className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-full bg-gradient-to-r from-white via-purple-50 to-indigo-100 px-6 py-3 text-sm font-bold text-indigo-950 shadow-xl shadow-purple-950/40 transition hover:bg-white hover:-translate-y-0.5 hover:shadow-2xl hover:shadow-purple-900/50 active:scale-95 ${
                      activeScene === 1 ? "animate-fade-up" : "opacity-0"
                    }`}
                    style={{ animationDelay: "1050ms" }}
                  >
                    <span>开始探索</span>
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </button>

                  <button
                    type="button"
                    onClick={() => router.push("/learning/practice")}
                    className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-semibold text-white backdrop-blur-md transition hover:bg-white/20 hover:-translate-y-0.5 active:scale-95 ${
                      activeScene === 1 ? "animate-fade-up" : "opacity-0"
                    }`}
                    style={{ animationDelay: "1150ms" }}
                  >
                    <Code2 className="h-4 w-4 text-emerald-400" />
                    <span>进入动手实践</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => router.push("/learning/portrait")}
                    className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-semibold text-white backdrop-blur-md transition hover:bg-white/20 hover:-translate-y-0.5 active:scale-95 ${
                      activeScene === 1 ? "animate-fade-up" : "opacity-0"
                    }`}
                    style={{ animationDelay: "1250ms" }}
                  >
                    <BarChart3 className="h-4 w-4 text-amber-400" />
                    <span>技能全景雷达</span>
                  </button>
                </div>
              </div>

              {/* ── 中层：继续上次（Resume HUD 浮空透光层） ────────────────── */}
              <section
                aria-labelledby="resume-hero-title"
                className={`mt-10 sm:mt-12 ${activeScene === 1 ? "animate-fade-up" : "opacity-0"}`}
                style={{ animationDelay: "1350ms" }}
              >
                <div className="workbench-hud-card p-5 sm:p-6">
                  <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-4">
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        <Sparkles className="h-3.5 w-3.5" />
                      </span>
                      <h3 id="resume-hero-title" className="text-lg font-bold tracking-tight text-white">
                        继续上次
                      </h3>
                    </div>
                  </div>

                  <div className="mt-4">
                    {loading && overviewState === "loading" ? (
                      <div className="space-y-3" role="status" aria-live="polite" aria-label="正在恢复最近记录">
                        <div className="h-4 w-2/3 animate-pulse rounded bg-white/10" />
                        <div className="h-4 w-1/2 animate-pulse rounded bg-white/10" />
                      </div>
                    ) : hasResumeEntry ? (
                      <ul className="space-y-2.5">
                        {practiceTopic && (
                          <ResumeRow
                            icon={<Zap className="h-4 w-4 text-amber-400" />}
                            label="上次停留在 · 动手实践"
                            value={practiceTopic}
                            href="/learning/practice"
                            action="继续练习"
                          />
                        )}
                        {latestTask && (
                          <ResumeRow
                            icon={<BriefcaseBusiness className="h-4 w-4 text-blue-400" />}
                            label="最近任务 · Task"
                            value={latestTask.title}
                            href={`/tasks/${latestTask.id}`}
                            action="打开任务"
                          />
                        )}
                        {latestConversation && (
                          <ResumeRow
                            icon={<Microscope className="h-4 w-4 text-purple-300" />}
                            label="最近科研 · Research"
                            value={latestConversation.topic ?? "未命名科研对话"}
                            href="/research"
                            action="进入科研"
                          />
                        )}
                      </ul>
                    ) : (
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between py-1">
                        <div>
                          <p className="font-mono text-xs tracking-wider text-purple-300 uppercase">
                            Quick Start
                          </p>
                          <p className="mt-1 text-base font-semibold text-white">
                            快速启航：完成你的第一次概念测验与探索
                          </p>
                          <p className="mt-1 text-sm text-purple-200/70">
                            从一个概念或问题进入学习，系统会随学习进展自动生成复盘与练习建议。
                          </p>
                        </div>
                        <Link
                          href="/learning"
                          className="inline-flex shrink-0 items-center gap-2 rounded-full bg-white/90 px-4 py-2 text-sm font-bold text-zinc-950 transition hover:bg-white hover:scale-105 active:scale-95"
                        >
                          进入学习
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              </section>

              {/* ── 下层：学习闭环与科研衔接（四大能力晶体卡片，极简凝练） ── */}
              <section
                aria-labelledby="capability-loop-title"
                className={`mt-10 sm:mt-12 ${activeScene === 1 ? "animate-fade-up" : "opacity-0"}`}
                style={{ animationDelay: "1450ms" }}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <h3 id="capability-loop-title" className="text-xl font-bold tracking-tight text-white">
                    学习闭环与科研衔接
                  </h3>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {capabilityCards.map((card) => {
                    const Icon = card.icon;
                    return (
                      <Link
                        key={card.href}
                        href={card.href}
                        className="group galaxy-card flex flex-col justify-between"
                      >
                        <div>
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-xs font-semibold tracking-wider text-white/50 bg-white/5 border border-white/10 px-2.5 py-0.5 rounded-full">
                              {card.index}
                            </span>
                            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/5 border border-white/10 text-white/70 group-hover:text-white group-hover:bg-white/10 group-hover:border-white/20 transition-all duration-200">
                              <Icon className="h-4 w-4 transition-transform duration-200 group-hover:scale-110" strokeWidth={1.75} />
                            </div>
                          </div>

                          <h4 className="mt-4 text-base sm:text-lg font-bold text-white tracking-tight group-hover:text-purple-100 transition-colors">
                            {card.title}
                          </h4>
                          <p className="mt-1 text-sm text-zinc-400 leading-relaxed font-normal">
                            {card.description}
                          </p>
                        </div>

                        <div className="mt-6 flex items-center justify-between pt-3.5 border-t border-white/8">
                          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-300 group-hover:text-white transition-colors">
                            <span>{card.cta}</span>
                            <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-1" />
                          </span>
                          {card.badge && (
                            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-purple-200 border border-white/15">
                              {card.badge}
                            </span>
                          )}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>

              {error && (
                <section
                  role="alert"
                  className="app-status-error mt-6 rounded-2xl p-4 text-sm"
                >
                  <p>{error}</p>
                  <button type="button" onClick={() => void load()} className="mt-2 font-semibold underline">
                    重试加载
                  </button>
                </section>
              )}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function ResumeRow({
  icon,
  label,
  value,
  href,
  action,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  href: string;
  action: string;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-white/8 bg-white/5 p-3.5 backdrop-blur-md transition hover:border-purple-400/40 hover:bg-white/10 hover:shadow-xs sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 border border-white/12">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-purple-300/90">{label}</p>
          <p className="truncate text-base font-bold text-white">
            {value}
          </p>
        </div>
      </div>
      <Link
        href={href}
        className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-full bg-white/90 px-3.5 py-1.5 text-xs font-bold text-zinc-950 shadow-xs transition hover:bg-white hover:scale-105 active:scale-95 sm:self-auto"
      >
        <span>{action}</span>
        <ArrowRight className="h-3 w-3" />
      </Link>
    </li>
  );
}
