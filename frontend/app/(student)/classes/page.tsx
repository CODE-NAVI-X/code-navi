"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  Check,
  ChevronRight,
  Copy,
  GraduationCap,
  Loader2,
  Plus,
  School,
  UserPlus,
  Users,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import {
  ClassApiError,
  type ClassroomItem,
  createClass,
  joinClass,
  listClasses,
} from "@/lib/api/classes";
import { useAuth } from "@/lib/context/auth-context";

export default function ClassesPage() {
  const router = useRouter();
  const { user, mode, loading: authLoading } = useAuth();

  const [classes, setClasses] = useState<ClassroomItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [classNameInput, setClassNameInput] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [justCreatedClass, setJustCreatedClass] = useState<ClassroomItem | null>(null);

  const [inviteCodeInput, setInviteCodeInput] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joinSuccess, setJoinSuccess] = useState<string | null>(null);

  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      if (authLoading) return;
      if (mode !== "authenticated" || !user) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const items = await listClasses();
        if (!cancelled) {
          setClasses(items);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "获取班级列表失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void fetchData();
    return () => {
      cancelled = true;
    };
  }, [authLoading, mode, user]);

  const handleCopyCode = async (code: string) => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
        setCopiedCode(code);
        setTimeout(() => setCopiedCode(null), 3000);
        return;
      }
    } catch {
      // Ignore clipboard API rejection
    }
    window.prompt("请手动复制班级邀请码：", code);
  };

  const handleCreateClass = async (e: FormEvent) => {
    e.preventDefault();
    const name = classNameInput.trim();
    if (!name) return;

    setCreating(true);
    setCreateError(null);
    setJustCreatedClass(null);

    try {
      const created = await createClass(name);
      setClassNameInput("");
      setJustCreatedClass(created);
      const updated = await listClasses();
      setClasses(updated);
    } catch (err: unknown) {
      if (err instanceof ClassApiError) {
        setCreateError(err.message);
      } else {
        setCreateError(err instanceof Error ? err.message : "创建班级失败");
      }
    } finally {
      setCreating(false);
    }
  };

  const handleJoinClass = async (e: FormEvent) => {
    e.preventDefault();
    const code = inviteCodeInput.trim();
    if (!code) return;

    setJoining(true);
    setJoinError(null);
    setJoinSuccess(null);

    try {
      const joined = await joinClass(code);
      setInviteCodeInput("");
      setJoinSuccess(`成功加入班级「${joined.name}」！`);
      const updated = await listClasses();
      setClasses(updated);
    } catch (err: unknown) {
      if (err instanceof ClassApiError) {
        setJoinError(err.message);
      } else {
        setJoinError(err instanceof Error ? err.message : "加入班级失败");
      }
    } finally {
      setJoining(false);
    }
  };

  if (!authLoading && (mode !== "authenticated" || !user)) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 text-center">
        <Card className="p-8">
          <School className="mx-auto h-12 w-12 text-slate-400 dark:text-zinc-600" />
          <h2 className="mt-4 text-lg font-semibold text-slate-900 dark:text-zinc-100">
            请先登录以访问班级功能
          </h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">
            登录后可创建属于您的教学班级，或凭教师提供的邀请码加入班级。
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button onClick={() => router.push("/login")}>去登录</Button>
            <Button variant="outline" onClick={() => router.push("/register")}>
              注册账号
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const isTeacher = user?.role === "teacher";
  const ownedClasses = classes.filter((c) => c.isOwner);
  const joinedClasses = classes.filter((c) => !c.isOwner);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-8">
      {/* 顶部标题与身份提示 */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200/80 pb-5 dark:border-zinc-800">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-zinc-100">
              班级管理
            </h1>
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800/50">
              <GraduationCap className="h-3 w-3" />
              当前身份：{isTeacher ? "教师" : "学生"}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">
            {isTeacher
              ? "作为教师，您可以创建班级并分发邀请码，集中管理班级学生成员。"
              : "作为学生，您可以输入教师提供的 8 位邀请码加入教学班级。"}
          </p>
        </div>
        <div className="shrink-0">
          <Link
            href="/account"
            className="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 hover:underline"
          >
            切换身份？去账户设置 &rarr;
          </Link>
        </div>
      </div>

      {error && (
        <Alert variant="error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* 操作卡片：教师创建班级 / 学生加入班级 */}
      {isTeacher ? (
        <Card className="border-blue-200/70 bg-gradient-to-br from-white to-blue-50/20 dark:border-blue-900/40 dark:from-zinc-900 dark:to-blue-950/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                <Plus className="h-4 w-4" />
              </div>
              <div>
                <CardTitle>创建新班级</CardTitle>
                <CardDescription>
                  输入班级名称创建班级，系统将自动生成 8 位不重复邀请码
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {createError && (
              <Alert variant="error">
                <AlertDescription>{createError}</AlertDescription>
              </Alert>
            )}

            {justCreatedClass && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 dark:border-emerald-900/60 dark:bg-emerald-950/30">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="text-xs font-semibold text-emerald-800 dark:text-emerald-300">
                      班级「{justCreatedClass.name}」创建成功！
                    </div>
                    <div className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">
                      班级邀请码：
                      <span className="font-mono text-base font-bold tracking-wider text-emerald-900 dark:text-emerald-200 ml-1">
                        {justCreatedClass.inviteCode}
                      </span>
                    </div>
                  </div>
                  {justCreatedClass.inviteCode && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleCopyCode(justCreatedClass.inviteCode!)}
                      className="border-emerald-300 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-800 dark:text-emerald-300"
                    >
                      {copiedCode === justCreatedClass.inviteCode ? (
                        <>
                          <Check className="mr-1.5 h-3.5 w-3.5" />
                          已复制
                        </>
                      ) : (
                        <>
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          复制邀请码
                        </>
                      )}
                    </Button>
                  )}
                </div>
              </div>
            )}

            <form onSubmit={handleCreateClass} className="flex flex-col gap-3 sm:flex-row">
              <div className="flex-1">
                <Label htmlFor="className" className="sr-only">
                  班级名称
                </Label>
                <Input
                  id="className"
                  placeholder="例如：2026级计算机科学与技术1班"
                  value={classNameInput}
                  onChange={(e) => setClassNameInput(e.target.value)}
                  disabled={creating}
                  maxLength={100}
                />
              </div>
              <Button type="submit" loading={creating} disabled={creating || !classNameInput.trim()}>
                创建班级
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-blue-200/70 bg-gradient-to-br from-white to-blue-50/20 dark:border-blue-900/40 dark:from-zinc-900 dark:to-blue-950/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                <UserPlus className="h-4 w-4" />
              </div>
              <div>
                <CardTitle>加入班级</CardTitle>
                <CardDescription>
                  请输入教师分享给您的 8 位字母/数字邀请码
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {joinError && (
              <Alert variant="error">
                <AlertDescription>{joinError}</AlertDescription>
              </Alert>
            )}
            {joinSuccess && (
              <Alert variant="success">
                <AlertDescription>{joinSuccess}</AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleJoinClass} className="flex flex-col gap-3 sm:flex-row">
              <div className="flex-1">
                <Label htmlFor="inviteCode" className="sr-only">
                  班级邀请码
                </Label>
                <Input
                  id="inviteCode"
                  placeholder="请输入 8 位邀请码（如 ABC23489）"
                  value={inviteCodeInput}
                  onChange={(e) => setInviteCodeInput(e.target.value.toUpperCase())}
                  disabled={joining}
                  maxLength={32}
                  className="font-mono uppercase tracking-wider"
                />
              </div>
              <Button type="submit" loading={joining} disabled={joining || !inviteCodeInput.trim()}>
                加入班级
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* 班级列表主体 */}
      <div className="space-y-6">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400 dark:text-zinc-600">
            <Loader2 className="h-6 w-6 animate-spin mr-2" />
            <span>正在加载班级信息...</span>
          </div>
        ) : (
          <>
            {/* 教师主列表 / 学生主列表 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-slate-900 dark:text-zinc-100">
                  {isTeacher ? "我创建的班级" : "我的班级"}
                </h2>
                <span className="text-xs text-slate-400 dark:text-zinc-500">
                  共 {(isTeacher ? ownedClasses : joinedClasses).length} 个班级
                </span>
              </div>

              {(isTeacher ? ownedClasses : joinedClasses).length === 0 ? (
                <Card className="border-dashed p-8 text-center">
                  <Users className="mx-auto h-8 w-8 text-slate-300 dark:text-zinc-700" />
                  <p className="mt-3 text-sm text-slate-500 dark:text-zinc-400">
                    {isTeacher
                      ? "您还没有创建任何班级。在上方输入班级名称即可创建。"
                      : "您尚未加入任何班级。在上方输入教师提供的邀请码即可加入。"}
                  </p>
                </Card>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {(isTeacher ? ownedClasses : joinedClasses).map((item) => (
                    <Card
                      key={item.id}
                      className="group relative overflow-hidden transition hover:border-slate-300 hover:shadow-md dark:hover:border-zinc-700"
                    >
                      <div className="p-5 flex flex-col justify-between h-full space-y-4">
                        <div className="space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <h3 className="font-semibold text-slate-900 group-hover:text-blue-600 dark:text-zinc-100 dark:group-hover:text-blue-400 transition line-clamp-1">
                              {item.name}
                            </h3>
                            <span className="inline-flex shrink-0 items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">
                              {item.roleInClass === "teacher" ? "教师" : "学生"}
                            </span>
                          </div>

                          <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-zinc-400">
                            <span className="flex items-center gap-1">
                              <Users className="h-3.5 w-3.5" />
                              {item.memberCount} 位成员
                            </span>
                            <span>创建于 {new Date(item.createdAt).toLocaleDateString()}</span>
                          </div>

                          {/* 仅教师/owner 可见并复制邀请码 */}
                          {item.isOwner && item.inviteCode && (
                            <div className="mt-3 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-xs border border-slate-200/60 dark:bg-zinc-800/40 dark:border-zinc-800">
                              <span className="text-slate-500 dark:text-zinc-400">邀请码：</span>
                              <div className="flex items-center gap-1.5 font-mono font-bold tracking-wider text-slate-800 dark:text-zinc-200">
                                <span>{item.inviteCode}</span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleCopyCode(item.inviteCode!);
                                  }}
                                  className="p-1 text-slate-400 hover:text-slate-700 dark:hover:text-zinc-200 transition"
                                  title="复制邀请码"
                                >
                                  {copiedCode === item.inviteCode ? (
                                    <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                                  ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                  )}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="pt-2 border-t border-slate-100 dark:border-zinc-800/60 flex justify-end">
                          <Link
                            href={`/classes/${item.id}`}
                            className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-500 dark:text-blue-400 transition"
                          >
                            查看成员名单
                            <ChevronRight className="h-3.5 w-3.5" />
                          </Link>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </div>

            {/* 跨身份容错展示：教师曾加入的班级 或 学生曾创建的班级 */}
            {isTeacher && joinedClasses.length > 0 && (
              <div className="space-y-3 pt-6 border-t border-slate-200/60 dark:border-zinc-800/60">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-zinc-300">
                  我加入的班级（历史学生身份）
                </h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {joinedClasses.map((item) => (
                    <Card key={item.id} className="p-4 flex items-center justify-between">
                      <div>
                        <div className="font-medium text-slate-800 dark:text-zinc-200 text-sm">
                          {item.name}
                        </div>
                        <div className="text-xs text-slate-400 dark:text-zinc-500 mt-1">
                          {item.memberCount} 位成员
                        </div>
                      </div>
                      <Link
                        href={`/classes/${item.id}`}
                        className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                      >
                        详情 &rarr;
                      </Link>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {!isTeacher && ownedClasses.length > 0 && (
              <div className="space-y-3 pt-6 border-t border-slate-200/60 dark:border-zinc-800/60">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-zinc-300">
                  我创建的班级（历史教师身份）
                </h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {ownedClasses.map((item) => (
                    <Card key={item.id} className="p-4 flex items-center justify-between">
                      <div>
                        <div className="font-medium text-slate-800 dark:text-zinc-200 text-sm">
                          {item.name}
                        </div>
                        <div className="text-xs text-slate-400 dark:text-zinc-500 mt-1 font-mono">
                          邀请码: {item.inviteCode} · {item.memberCount} 位成员
                        </div>
                      </div>
                      <Link
                        href={`/classes/${item.id}`}
                        className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                      >
                        详情 &rarr;
                      </Link>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
