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
import { AlertCircle, Eye, EyeOff, Lock, Mail, User } from "lucide-react";

function sanitizeNextUrl(next: string | null): string {
  if (!next) return "/";
  if (next.startsWith("/") && !next.startsWith("//") && !next.includes(":")) {
    return next;
  }
  return "/";
}

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextParam = searchParams.get("next");
  const targetUrl = sanitizeNextUrl(nextParam);

  const { register, mode, user } = useAuth();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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

    if (!displayName.trim()) {
      setError("请输入用户昵称");
      return;
    }
    if (!email.trim()) {
      setError("请输入电子邮箱");
      return;
    }
    if (password.length < 8) {
      setError("密码长度至少为 8 位");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await register(email.trim(), password, displayName.trim(), true);
      router.push(targetUrl);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("注册失败，请稍后再试");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full shadow-lg border-slate-200/90 dark:border-zinc-800">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold">创建新账号</CardTitle>
        <CardDescription>
          加入 Code Navi，开启结构化编程学习与学术科研探索之旅
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
            <Label htmlFor="displayName" required>
              用户昵称
            </Label>
            <Input
              id="displayName"
              type="text"
              placeholder="例如：林同学"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={loading}
              leftIcon={<User className="w-4 h-4" />}
              autoComplete="name"
              required
            />
          </div>

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
            <Label htmlFor="password" required>
              设置密码
            </Label>
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="至少 8 位包含字母和数字"
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
              autoComplete="new-password"
              required
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="confirmPassword" required>
              确认密码
            </Label>
            <Input
              id="confirmPassword"
              type={showPassword ? "text" : "password"}
              placeholder="再次输入相同密码"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={loading}
              leftIcon={<Lock className="w-4 h-4" />}
              autoComplete="new-password"
              required
            />
          </div>

          <Button
            type="submit"
            className="w-full mt-3"
            size="md"
            loading={loading}
          >
            创建账号
          </Button>
        </form>
      </CardContent>

      <CardFooter className="justify-center">
        <p className="text-xs text-slate-500 dark:text-zinc-400">
          已有账号？{" "}
          <Link
            href={`/login${nextParam ? `?next=${encodeURIComponent(nextParam)}` : ""}`}
            className="font-semibold text-slate-900 dark:text-zinc-100 hover:underline inline-flex items-center gap-0.5"
          >
            直接登录
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-slate-500">正在加载...</div>}>
      <RegisterForm />
    </Suspense>
  );
}
