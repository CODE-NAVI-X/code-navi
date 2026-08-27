"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi } from "@/lib/api/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Alert, AlertDescription } from "@/components/ui/Alert";
import { AlertCircle, CheckCircle2, Eye, EyeOff, KeyRound, Lock } from "lucide-react";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryToken = searchParams.get("token") || "";

  const [token, setToken] = useState(queryToken);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!token.trim()) {
      setError("缺少重置凭证（Token），请检查邮件重置链接");
      return;
    }
    if (newPassword.length < 8) {
      setError("密码长度至少为 8 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await authApi.resetPassword(token.trim(), newPassword);
      setSuccess(true);
      setTimeout(() => {
        router.push("/login");
      }, 2500);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("密码重置失败，可能链接已过期");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full shadow-lg border-slate-200/90 dark:border-zinc-800">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold">重置密码</CardTitle>
        <CardDescription>
          请为您的 Code Navi 账号设置一个新的安全登录密码
        </CardDescription>
      </CardHeader>

      <CardContent>
        {success ? (
          <div className="space-y-5 text-center py-3">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-6 w-6" />
            </div>

            <div className="space-y-1">
              <h4 className="text-base font-semibold text-slate-900 dark:text-zinc-100">
                密码重置成功！
              </h4>
              <p className="text-xs text-slate-500 dark:text-zinc-400">
                您的密码已成功更新，即将自动跳转至登录界面...
              </p>
            </div>

            <div className="pt-2">
              <Link href="/login">
                <Button className="w-full text-xs">立即登录</Button>
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <Alert variant="error" icon={<AlertCircle className="w-4 h-4" />}>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {!queryToken && (
              <div className="space-y-1">
                <Label htmlFor="token" required>
                  重置凭证码 (Token)
                </Label>
                <Input
                  id="token"
                  type="text"
                  placeholder="邮件中收到的重置 Token"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  disabled={loading}
                  leftIcon={<KeyRound className="w-4 h-4" />}
                  required
                />
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="newPassword" required>
                新密码
              </Label>
              <Input
                id="newPassword"
                type={showPassword ? "text" : "password"}
                placeholder="至少 8 位包含字母和数字"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
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
                确认新密码
              </Label>
              <Input
                id="confirmPassword"
                type={showPassword ? "text" : "password"}
                placeholder="再次输入新密码"
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
              className="w-full mt-2"
              size="md"
              loading={loading}
            >
              确认修改密码
            </Button>
          </form>
        )}
      </CardContent>

      {!success && (
        <CardFooter className="justify-center">
          <Link
            href="/login"
            className="text-xs font-medium text-slate-600 dark:text-zinc-400 hover:text-slate-900 dark:hover:text-zinc-100"
          >
            返回登录
          </Link>
        </CardFooter>
      )}
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-slate-500">正在加载...</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
