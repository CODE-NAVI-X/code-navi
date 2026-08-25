"use client";

import React, { useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/api/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Alert, AlertDescription } from "@/components/ui/Alert";
import { AlertCircle, ArrowLeft, CheckCircle2, Mail } from "lucide-react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("请输入注册时使用的电子邮箱");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await authApi.forgotPassword(email.trim());
      setSubmitted(true);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("发送重置请求失败，请稍后再试");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full shadow-lg border-slate-200/90 dark:border-zinc-800">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl font-bold">找回密码</CardTitle>
        <CardDescription>
          输入您的注册邮箱，我们将向您发送重置密码的邮件链接
        </CardDescription>
      </CardHeader>

      <CardContent>
        {submitted ? (
          <div className="space-y-5 text-center py-2">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-6 w-6" />
            </div>

            <div className="space-y-1.5">
              <h4 className="text-base font-semibold text-slate-900 dark:text-zinc-100">
                重置邮件已发出
              </h4>
              <p className="text-xs text-slate-500 dark:text-zinc-400 leading-relaxed max-w-sm mx-auto">
                如果 <span className="font-medium text-slate-800 dark:text-zinc-200">{email}</span> 已在 Code Navi 注册，您将收到一封包含密码重置链接的邮件。重置链接有效时间为 30 分钟。
              </p>
            </div>

            <div className="pt-2">
              <Link href="/login">
                <Button variant="outline" className="w-full text-xs">
                  返回登录页面
                </Button>
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

            <div className="space-y-1">
              <Label htmlFor="email" required>
                注册邮箱
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

            <Button
              type="submit"
              className="w-full mt-2"
              size="md"
              loading={loading}
            >
              发送重置链接
            </Button>
          </form>
        )}
      </CardContent>

      {!submitted && (
        <CardFooter className="justify-center">
          <Link
            href="/login"
            className="text-xs font-medium text-slate-600 dark:text-zinc-400 hover:text-slate-900 dark:hover:text-zinc-100 inline-flex items-center gap-1"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            返回登录
          </Link>
        </CardFooter>
      )}
    </Card>
  );
}
