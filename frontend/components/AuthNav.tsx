"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/context/auth-context";
import {
  LanguageBasicsPreference,
  readLanguageBasics,
  saveLanguageBasics,
} from "@/lib/language-basics";
import { getOrCreateLearnerId } from "@/lib/learner";
import {
  User,
  LogIn,
  UserPlus,
  LogOut,
  ChevronDown,
  Settings,
} from "lucide-react";

export function AuthNav(): React.ReactElement {
  const router = useRouter();
  const { mode, user, loading, logout } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [languageDialogOpen, setLanguageDialogOpen] = useState(false);
  const [languageBasics, setLanguageBasics] = useState<LanguageBasicsPreference>(() =>
    readLanguageBasics(getOrCreateLearnerId()),
  );
  const [pendingLanguageBasics, setPendingLanguageBasics] =
    useState<LanguageBasicsPreference>(languageBasics);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logout();
      setDropdownOpen(false);
      router.push("/login");
    } finally {
      setLoggingOut(false);
    }
  };

  const confirmLanguageBasics = () => {
    if (pendingLanguageBasics === "unknown") return;
    const learnerId = getOrCreateLearnerId();
    saveLanguageBasics(learnerId, pendingLanguageBasics);
    setLanguageBasics(pendingLanguageBasics);
    setLanguageDialogOpen(false);
    setDropdownOpen(false);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2">
        <div className="h-8 w-20 animate-pulse rounded-lg bg-slate-200/80 dark:bg-zinc-800" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 relative" ref={dropdownRef}>
      {mode === "authenticated" && user ? (
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-xs hover:bg-slate-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800 cursor-pointer transition-colors focus:outline-none"
          >
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 text-[11px] font-bold text-white shadow-xs">
              {user.displayName ? user.displayName.slice(0, 1).toUpperCase() : "U"}
            </div>
            <span className="max-w-[110px] truncate font-medium text-slate-900 dark:text-zinc-100">
              {user.displayName}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400 dark:text-zinc-500" />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900 z-50 text-xs animate-in fade-in zoom-in-95 duration-100">
              <div className="px-2.5 py-2 border-b border-slate-100 dark:border-zinc-800/80">
                <p className="font-semibold text-slate-900 dark:text-zinc-100 truncate">
                  {user.displayName}
                </p>
                <p className="text-[11px] text-slate-500 dark:text-zinc-400 truncate mt-0.5">
                  {user.email}
                </p>
              </div>

              <div className="py-1">
                <Link
                  href="/portrait"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <User className="h-3.5 w-3.5 text-slate-400" />
                  <span>学习画像与数据</span>
                </Link>
                <Link
                  href="/account"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <Settings className="h-3.5 w-3.5 text-slate-400" />
                  <span>账户设置</span>
                </Link>
                <button
                  type="button"
                  onClick={() => {
                    setDropdownOpen(false);
                    setLanguageDialogOpen(true);
                  }}
                  className="flex w-full items-center gap-2 px-2.5 py-1.5 rounded-lg text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors text-left"
                >
                  <Settings className="h-3.5 w-3.5 text-slate-400" />
                  <span>语言基础设置</span>
                </button>
              </div>

              <div className="pt-1 border-t border-slate-100 dark:border-zinc-800/80">
                <button
                  onClick={handleLogout}
                  disabled={loggingOut}
                  className="flex w-full items-center gap-2 px-2.5 py-1.5 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors cursor-pointer disabled:opacity-50"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>{loggingOut ? "正在退出..." : "退出登录"}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200/90 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-xs hover:bg-slate-50 hover:text-slate-950 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white transition-colors"
          >
            <LogIn className="h-3.5 w-3.5" />
            登录
          </Link>
          <Link
            href="/register"
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-slate-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200 transition-colors"
          >
            <UserPlus className="h-3.5 w-3.5" />
            免费注册
          </Link>
        </div>
      )}

      {languageDialogOpen ? (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-zinc-700 dark:bg-zinc-900">
            <h2 className="text-lg font-bold text-slate-950 dark:text-zinc-50">
              语言基础设置
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-300">
              选择后会影响 Practice 首页推荐的练习题。之后可以随时回来修改。
            </p>
            <div className="mt-5 grid gap-2">
              <button
                type="button"
                onClick={() => setPendingLanguageBasics("has_basics")}
                className={`rounded-xl px-4 py-3 text-left text-sm font-semibold ${
                  pendingLanguageBasics === "has_basics"
                    ? "bg-slate-950 text-white dark:bg-zinc-100 dark:text-zinc-950"
                    : "bg-slate-100 text-slate-800 dark:bg-zinc-800 dark:text-zinc-100"
                }`}
              >
                有基础，直接练习算法与框架结构
              </button>
              <button
                type="button"
                onClick={() => setPendingLanguageBasics("no_basics")}
                className={`rounded-xl px-4 py-3 text-left text-sm font-semibold ${
                  pendingLanguageBasics === "no_basics"
                    ? "bg-slate-950 text-white dark:bg-zinc-100 dark:text-zinc-950"
                    : "bg-slate-100 text-slate-800 dark:bg-zinc-800 dark:text-zinc-100"
                }`}
              >
                没有基础，先练习基础语法
              </button>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  setPendingLanguageBasics(languageBasics);
                  setLanguageDialogOpen(false);
                }}
                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 dark:border-zinc-700 dark:text-zinc-300"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmLanguageBasics}
                disabled={pendingLanguageBasics === "unknown"}
                className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-950"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
