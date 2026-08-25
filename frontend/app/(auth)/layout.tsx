import React from "react";
import Link from "next/link";
import { BookOpen, Code2, Compass, GraduationCap, Sparkles } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen w-full flex bg-slate-50 dark:bg-zinc-950 font-sans">
      {/* Left side: Brand Showcase (Hidden on mobile) */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-slate-900 dark:bg-zinc-900 text-white flex-col justify-between p-12 overflow-hidden border-r border-slate-800/80">
        {/* Subtle decorative background gradients */}
        <div className="absolute -top-24 -left-24 w-96 h-96 bg-blue-600/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-indigo-600/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-1/2 left-1/3 w-64 h-64 bg-emerald-600/10 rounded-full blur-3xl pointer-events-none" />

        {/* Top brand header */}
        <div className="relative z-10">
          <Link
            href="/"
            className="inline-flex items-center gap-2.5 text-xl font-bold tracking-tight text-white hover:opacity-90 transition-opacity"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 shadow-md">
              <Compass className="h-5 w-5 text-white" />
            </div>
            <span>Code Navi</span>
          </Link>
          <p className="mt-2 text-xs font-medium text-slate-400">
            面向学习、实践与科研探索的智能辅助平台
          </p>
        </div>

        {/* Feature Highlights Showcase */}
        <div className="relative z-10 my-auto py-8 space-y-6 max-w-lg">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/60 text-xs text-blue-400 font-medium">
            <Sparkles className="w-3.5 h-3.5" />
            <span>三位一体智能学习架构</span>
          </div>

          <h2 className="text-3xl font-extrabold tracking-tight text-white leading-tight">
            从知识掌握到算法实践，<br />
            再到深度科研探索。
          </h2>

          <div className="space-y-4 pt-2">
            <div className="flex items-start gap-3.5 p-3.5 rounded-xl bg-slate-800/40 border border-slate-700/40 backdrop-blur-xs">
              <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 shrink-0 mt-0.5">
                <BookOpen className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-200">
                  自适应学习与演示生成
                </h4>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                  多角色知识拆解、LaTeX 数学公式呈现、实时大纲与幻灯片交互演示。
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3.5 p-3.5 rounded-xl bg-slate-800/40 border border-slate-700/40 backdrop-blur-xs">
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 shrink-0 mt-0.5">
                <Code2 className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-200">
                  真实 Python 代码沙箱与评测
                </h4>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                  确定性规则判题、AI 启发式辅导与学情知识缺口诊断。
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3.5 p-3.5 rounded-xl bg-slate-800/40 border border-slate-700/40 backdrop-blur-xs">
              <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 shrink-0 mt-0.5">
                <GraduationCap className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-200">
                  严谨学术科研引导与跨源检索
                </h4>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">
                  OpenAlex / Crossref / arXiv 真实验证、思维导图构建与两周 MVP 计划。
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer info */}
        <div className="relative z-10 text-xs text-slate-500">
          <p>© 2026 Code Navi. All rights reserved.</p>
        </div>
      </div>

      {/* Right side: Interactive Auth Forms */}
      <div className="flex-1 flex flex-col justify-center items-center p-6 sm:p-12 overflow-y-auto">
        <div className="w-full max-w-md my-auto">
          {/* Mobile brand header */}
          <div className="lg:hidden flex items-center justify-center gap-2 mb-8">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 dark:bg-zinc-100 text-white dark:text-zinc-900 shadow-sm">
              <Compass className="h-4 w-4" />
            </div>
            <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-zinc-100">
              Code Navi
            </span>
          </div>

          {children}
        </div>
      </div>
    </div>
  );
}
