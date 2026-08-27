"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/context/auth-context";
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
    </div>
  );
}
