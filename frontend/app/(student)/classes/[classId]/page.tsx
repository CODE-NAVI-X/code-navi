"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Calendar,
  Check,
  Copy,
  Edit3,
  GraduationCap,
  Loader2,
  Lock,
  Mail,
  Save,
  School,
  Shield,
  Trash2,
  UserCheck,
  Users,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  Card,
  CardContent,
  CardDescription,
  CardTitle,
} from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import {
  ClassApiError,
  type ClassroomItem,
  type ClassroomMember,
  getClassMembers,
  getClassroom,
  removeClassMember,
  updateMemberNote,
} from "@/lib/api/classes";
import { useAuth } from "@/lib/context/auth-context";

export default function ClassDetailPage() {
  const params = useParams<{ classId: string }>();
  const classId = params.classId;
  const { user, loading: authLoading } = useAuth();

  const [classroom, setClassroom] = useState<ClassroomItem | null>(null);
  const [members, setMembers] = useState<ClassroomMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Teacher member note editing state
  const [editingNoteUserId, setEditingNoteUserId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  // Teacher member removal state
  const [selectedRemoveMember, setSelectedRemoveMember] = useState<ClassroomMember | null>(null);
  const [removingMember, setRemovingMember] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (authLoading) return;
      if (!classId) return;

      setLoading(true);
      setError(null);

      try {
        const [cls, mems] = await Promise.all([
          getClassroom(classId),
          getClassMembers(classId),
        ]);
        if (!cancelled) {
          setClassroom(cls);
          setMembers(mems);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          if (err instanceof ClassApiError && err.status === 404) {
            setError("班级不存在或您无权访问该班级");
          } else {
            setError(err instanceof Error ? err.message : "获取班级信息失败");
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [classId, authLoading]);

  const handleCopyCode = async (code: string) => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 3000);
        return;
      }
    } catch {
      // Ignore clipboard API rejection
    }
    window.prompt("请手动复制班级邀请码：", code);
  };

  const handleStartEditNote = (member: ClassroomMember) => {
    setEditingNoteUserId(member.userId);
    setNoteDraft(member.note || "");
    setActionError(null);
  };

  const handleSaveNote = async (userId: string) => {
    if (!classId) return;
    setSavingNote(true);
    setActionError(null);
    try {
      const updated = await updateMemberNote(classId, userId, noteDraft.trim() || null);
      setMembers((prev) =>
        prev.map((m) => (m.userId === userId ? { ...m, note: updated.note } : m))
      );
      setEditingNoteUserId(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "保存备注失败");
    } finally {
      setSavingNote(false);
    }
  };

  const handleConfirmRemove = async () => {
    if (!classId || !selectedRemoveMember) return;
    setRemovingMember(true);
    setActionError(null);
    try {
      await removeClassMember(classId, selectedRemoveMember.userId);
      setMembers((prev) => prev.filter((m) => m.userId !== selectedRemoveMember.userId));
      setSelectedRemoveMember(null);
      if (classroom) {
        setClassroom({ ...classroom, memberCount: Math.max(1, classroom.memberCount - 1) });
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "移除成员失败");
    } finally {
      setRemovingMember(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-16 text-center">
        <div className="flex flex-col items-center justify-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600 dark:text-blue-400" />
          <p className="text-sm text-slate-500 dark:text-zinc-400">
            正在获取班级及成员名单...
          </p>
        </div>
      </div>
    );
  }

  if (error || !classroom) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <Card className="p-8 text-center">
          <Lock className="mx-auto h-12 w-12 text-slate-400 dark:text-zinc-600" />
          <h2 className="mt-4 text-lg font-semibold text-slate-900 dark:text-zinc-100">
            {error || "班级不存在或您无权访问"}
          </h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">
            您可能不是该班级的教师或成员，或者该班级已被移除。
          </p>
          <div className="mt-6 flex justify-center">
            <Link href="/classes">
              <Button variant="outline">
                <ArrowLeft className="mr-2 h-4 w-4" />
                返回班级列表
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
      {/* 返回导航 */}
      <div>
        <Link
          href="/classes"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 dark:text-zinc-400 dark:hover:text-zinc-100 transition"
        >
          <ArrowLeft className="h-4 w-4" />
          返回所有班级
        </Link>
      </div>

      {/* 班级信息头部卡片 */}
      <Card className="overflow-hidden border-slate-200/80 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="border-b border-slate-100 bg-slate-50/50 p-6 dark:border-zinc-800/80 dark:bg-zinc-900/50">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-100 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                  <School className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-slate-900 dark:text-zinc-100">
                    {classroom.name}
                  </h1>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-zinc-400 mt-1">
                    <span className="inline-flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      创建于 {new Date(classroom.createdAt).toLocaleDateString()}
                    </span>
                    <span>·</span>
                    <span className="inline-flex items-center gap-1">
                      <Users className="h-3 w-3" />
                      {members.length} 位成员
                    </span>
                    <span>·</span>
                    <span className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 font-medium">
                      <UserCheck className="h-3 w-3" />
                      您的身份：{classroom.roleInClass === "teacher" ? "教师" : "学生"}
                      {classroom.isOwner ? " (创建者)" : ""}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* 仅创建者教师展示邀请码卡片 */}
            {classroom.isOwner && classroom.inviteCode && (
              <div className="flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50/60 p-3 dark:border-blue-900/60 dark:bg-blue-950/40">
                <div>
                  <div className="text-[11px] text-blue-600 dark:text-blue-400 font-medium">
                    班级邀请码
                  </div>
                  <div className="font-mono text-lg font-bold tracking-wider text-blue-950 dark:text-blue-100">
                    {classroom.inviteCode}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopyCode(classroom.inviteCode!)}
                  className="border-blue-300 text-blue-700 hover:bg-blue-100 dark:border-blue-800 dark:text-blue-300"
                >
                  {copied ? (
                    <>
                      <Check className="mr-1.5 h-3.5 w-3.5" />
                      已复制
                    </>
                  ) : (
                    <>
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      复制
                    </>
                  )}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* 成员名单区域 */}
        <CardContent className="p-6">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-zinc-800/80">
            <div>
              <CardTitle>班级成员名单</CardTitle>
              <CardDescription className="mt-1 flex items-center gap-1 text-xs">
                <Shield className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                {classroom.isOwner
                  ? "作为班级所有者，您可以查看成员邮箱、设置私有教学备注并管理成员名单。"
                  : "出于隐私保护，成员名单仅显示姓名与班级身份，不展示邮箱地址。"}
              </CardDescription>
            </div>
            <span className="text-xs text-slate-400 dark:text-zinc-500">
              共 {members.length} 人
            </span>
          </div>

          <div className="mt-4 divide-y divide-slate-100 dark:divide-zinc-800/60">
            {members.map((member) => {
              const canRemove = classroom.isOwner && member.userId !== user?.id;

              return (
                <div
                  key={member.userId}
                  className="flex flex-col sm:flex-row sm:items-center sm:justify-between py-4 first:pt-0 last:pb-0 gap-3"
                >
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                        member.roleInClass === "teacher"
                          ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                          : "bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300"
                      }`}
                    >
                      {member.displayName.slice(0, 1) || "用"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-slate-900 dark:text-zinc-100">
                          {member.displayName}
                        </span>
                        {member.userId === user?.id && (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-zinc-800 dark:text-zinc-400">
                            我自己
                          </span>
                        )}
                        {/* 教师视角下展示邮箱 */}
                        {classroom.isOwner && member.email && (
                          <span className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-zinc-400">
                            <Mail className="h-3 w-3" />
                            {member.email}
                          </span>
                        )}
                      </div>

                      <div className="text-xs text-slate-400 dark:text-zinc-500 mt-0.5">
                        加入时间：{new Date(member.joinedAt).toLocaleString()}
                      </div>

                      {/* 教师私有备注区 */}
                      {classroom.isOwner && (
                        <div className="mt-2">
                          {editingNoteUserId === member.userId ? (
                            <div className="flex items-center gap-2 max-w-md">
                              <Input
                                value={noteDraft}
                                onChange={(e) => setNoteDraft(e.target.value)}
                                placeholder="添加私有教学备注（仅教师可见，最多500字）"
                                className="h-7 text-xs"
                                maxLength={500}
                                disabled={savingNote}
                                autoFocus
                              />
                              <Button
                                size="sm"
                                variant="primary"
                                className="h-7 px-2.5 text-xs shrink-0"
                                onClick={() => handleSaveNote(member.userId)}
                                loading={savingNote}
                              >
                                <Save className="h-3 w-3 mr-1" />
                                保存
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-xs shrink-0"
                                onClick={() => {
                                  setEditingNoteUserId(null);
                                  setActionError(null);
                                }}
                                disabled={savingNote}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <span className="inline-flex items-center text-xs text-slate-600 dark:text-zinc-300 bg-slate-50 dark:bg-zinc-800/60 px-2 py-0.5 rounded border border-slate-200/60 dark:border-zinc-700/60">
                                备注：{member.note || "暂无备注"}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleStartEditNote(member)}
                                className="text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors p-0.5 rounded"
                                title="编辑私有备注"
                              >
                                <Edit3 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-end sm:self-center shrink-0">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                        member.roleInClass === "teacher"
                          ? "bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800/60"
                          : "bg-slate-100 text-slate-600 border border-slate-200/80 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700"
                      }`}
                    >
                      <GraduationCap className="h-3 w-3" />
                      {member.roleInClass === "teacher" ? "教师" : "学生"}
                    </span>

                    {/* 移除学生按钮（仅所有者且非自身） */}
                    {canRemove && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedRemoveMember(member)}
                        className="text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30 h-7 px-2 text-xs"
                      >
                        <Trash2 className="h-3.5 w-3.5 mr-1" />
                        移出
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 移出班级确认弹窗 */}
      {selectedRemoveMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900 animate-in fade-in zoom-in-95 duration-150">
            <h3 className="font-semibold text-slate-900 dark:text-zinc-100 text-sm">
              移出班级确认
            </h3>
            <p className="mt-2 text-xs text-slate-600 dark:text-zinc-400 leading-relaxed">
              确认将学生 <span className="font-semibold text-slate-900 dark:text-zinc-100">{selectedRemoveMember.displayName}</span> 移出班级吗？
              移出后学生将无法访问本班级内容，但可重新凭邀请码加入。
            </p>
            {actionError && (
              <div className="mt-3 rounded bg-red-50 p-2 text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400">
                {actionError}
              </div>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedRemoveMember(null);
                  setActionError(null);
                }}
                disabled={removingMember}
              >
                取消
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleConfirmRemove}
                loading={removingMember}
              >
                确认移出
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
