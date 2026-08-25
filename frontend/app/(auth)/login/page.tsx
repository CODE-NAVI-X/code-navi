"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/context/auth-context";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Alert, AlertDescription } from "@/components/ui/Alert";
import { AlertCircle, ArrowRight, Eye, EyeOff, Lock, Mail, UserCheck } from "lucide-react";

function sanitizeNextUrl(next: string | null): string {
  if (!next) return "/";
  // Protect against open redirects: only allow relative paths starting with / (and not //)
  if (next.startsWith("/") && !next.startsWith("//") && !next.includes(":")) {
    return next;
  }
  return "/";
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextParam = searchParams.get("next");
  const targetUrl = sanitizeNextUrl(nextParam);

  const { login, mode, user } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already authenticated, redirect immediately
  React.useEffect(() => {
    if (mode === "authenticated" && user) {
      router.push(targetUrl);
    }
  }, [mode, user, router, targetUrl]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("请填写邮箱和密码");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await login(email.trim(), password, rememberMe, true);
      router.push(targetUrl);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("登录失败，请检查账号与密码");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGuestContinue = () => {
    router.push(targetUrl);
  };

  return (
    <Card className="w-full shadow-lg border-slate-200/90 dark:border-zinc-800">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold">欢迎回来</CardTitle>
        <CardDescription>
          登录您的 Code Navi 账号以同步工作区、科研对话与学习记录
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <Alert variant="error" icon={<AlertCircle className="w-4 h-4" />}>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-1">
            <Label htmlFor="email" required>
              电子邮箱
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="student@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              leftIcon={<Mail className="w-4 h-4" />}
              autoComplete="email"
              required
            />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label htmlFor="password" required>
                登录密码
              </Label>
              <Link
                href="/forgot-password"
                className="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 hover:underline"
              >
                忘记密码？
              </Link>
            </div>
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              leftIcon={<Lock className="w-4 h-4" />}
              rightIcon={
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              }
              autoComplete="current-password"
              required
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="rounded border-slate-300 dark:border-zinc-700 text-slate-900 focus:ring-slate-900 dark:bg-zinc-800 h-4 w-4"
              />
              <span className="text-xs text-slate-600 dark:text-zinc-400">
                记住登录状态 (30天)
              </span>
            </label>
          </div>

          <Button
            type="submit"
            className="w-full mt-2"
            size="md"
            loading={loading}
          >
            立即登录
          </Button>
        </form>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200 dark:border-zinc-800" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-white dark:bg-zinc-900 px-2 text-slate-400 dark:text-zinc-500">
              或
            </span>
          </div>
        </div>

        <Button
          type="button"
          variant="outline"
          className="w-full text-xs"
          onClick={handleGuestContinue}
        >
          <UserCheck className="w-4 h-4 mr-2 text-slate-500" />
          以游客身份继续探索
        </Button>
      </CardContent>

      <CardFooter className="justify-center">
        <p className="text-xs text-slate-500 dark:text-zinc-400">
          还没有账号？{" "}
          <Link
            href={`/register${nextParam ? `?next=${encodeURIComponent(nextParam)}` : ""}`}
            className="font-semibold text-slate-900 dark:text-zinc-100 hover:underline inline-flex items-center gap-0.5"
          >
            免费注册
            <ArrowRight className="w-3 h-3" />
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-slate-500">正在加载...</div>}>
      <LoginForm />
    </Suspense>
  );
}
