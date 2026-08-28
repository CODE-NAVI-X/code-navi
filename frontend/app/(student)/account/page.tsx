"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/context/auth-context";
import {
  authApi,
  AuthApiError,
  AuthSessionItem,
} from "@/lib/api/auth";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/Alert";
import {
  User,
  Mail,
  KeyRound,
  Laptop,
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  RefreshCw,
  LogOut,
  ShieldCheck,
  Smartphone,
  Trash2,
  GraduationCap,
  BookOpen,
} from "lucide-react";

export default function AccountSettingsPage(): React.ReactElement {
  const router = useRouter();
  const { user, mode, loading: authLoading, refreshSession, logout, changeRole } = useAuth();

  const [activeTab, setActiveTab] = useState<"profile" | "role" | "email" | "password" | "sessions" | "danger">("profile");
  const [toastMessage, setToastMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const showToast = (text: string, type: "success" | "error" = "success") => {
    setToastMessage({ type, text });
    setTimeout(() => setToastMessage(null), 5000);
  };

  // Redirect if guest/unauthenticated once loaded
  useEffect(() => {
    if (!authLoading && (mode !== "authenticated" || !user)) {
      router.push("/login");
    }
  }, [authLoading, mode, user, router]);

  // -------------------------------------------------------------
  // Role Section State
  // -------------------------------------------------------------
  const [selectedRole, setSelectedRole] = useState<"student" | "teacher">(user?.role ?? "student");
  const [changingRole, setChangingRole] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [showRoleConfirmModal, setShowRoleConfirmModal] = useState(false);

  const currentRole = user?.role ?? "student";

  const handleOpenRoleConfirm = (e: React.FormEvent) => {
    e.preventDefault();
    setRoleError(null);
    setShowRoleConfirmModal(true);
  };

  const handleConfirmRoleChange = async () => {
    setShowRoleConfirmModal(false);
    setChangingRole(true);
    setRoleError(null);
    try {
      await changeRole(selectedRole);
      setSelectedRole(selectedRole);
      showToast("身份已切换");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setRoleError(err.message);
      } else {
        setRoleError("切换身份失败，请重试");
      }
    } finally {
      setChangingRole(false);
    }
  };

  // -------------------------------------------------------------
  // Profile Section State
  // -------------------------------------------------------------
  const [displayName, setDisplayName] = useState(user?.displayName || "");
  const [updatingProfile, setUpdatingProfile] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError(null);
    if (!displayName.trim()) {
      setProfileError("昵称不能为空");
      return;
    }
    setUpdatingProfile(true);
    try {
      await authApi.updateMe(displayName.trim());
      await refreshSession();
      showToast("个人资料修改成功");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setProfileError(err.message);
      } else {
        setProfileError("修改失败，请重试");
      }
    } finally {
      setUpdatingProfile(false);
    }
  };

  // -------------------------------------------------------------
  // Email Verification State
  // -------------------------------------------------------------
  const [sendingVerifyEmail, setSendingVerifyEmail] = useState(false);
  const [verifyToken, setVerifyToken] = useState("");
  const [confirmingVerify, setConfirmingVerify] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const handleSendVerificationEmail = async () => {
    setVerifyError(null);
    setSendingVerifyEmail(true);
    try {
      await authApi.requestEmailVerification();
      showToast("验证邮件已发送，开发环境下请在后端日志查看 Token");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setVerifyError(err.message);
      } else {
        setVerifyError("发送失败，请稍后重试");
      }
    } finally {
      setSendingVerifyEmail(false);
    }
  };

  const handleConfirmVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    setVerifyError(null);
    if (!verifyToken.trim()) {
      setVerifyError("请输入验证 Token");
      return;
    }
    setConfirmingVerify(true);
    try {
      await authApi.confirmEmailVerification(verifyToken.trim());
      await refreshSession();
      setVerifyToken("");
      showToast("邮箱验证成功！");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setVerifyError(err.message);
      } else {
        setVerifyError("验证失败，请确认 Token 是否有效或过期");
      }
    } finally {
      setConfirmingVerify(false);
    }
  };

  // -------------------------------------------------------------
  // Email Change State
  // -------------------------------------------------------------
  const [newEmail, setNewEmail] = useState("");
  const [changeEmailPassword, setChangeEmailPassword] = useState("");
  const [showChangeEmailPassword, setShowChangeEmailPassword] = useState(false);
  const [requestingEmailChange, setRequestingEmailChange] = useState(false);
  const [changeEmailStep, setChangeEmailStep] = useState<1 | 2>(1);
  const [changeEmailToken, setChangeEmailToken] = useState("");
  const [confirmingEmailChange, setConfirmingEmailChange] = useState(false);
  const [emailChangeError, setEmailChangeError] = useState<string | null>(null);

  const handleRequestEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailChangeError(null);
    if (!newEmail.trim() || !changeEmailPassword) {
      setEmailChangeError("请填写完整信息");
      return;
    }
    setRequestingEmailChange(true);
    try {
      await authApi.requestEmailChange(newEmail.trim(), changeEmailPassword);
      setChangeEmailStep(2);
      showToast("换绑验证邮件已发送，开发环境下请在后端日志查看 Token");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setEmailChangeError(err.message);
      } else {
        setEmailChangeError("请求失败，请检查密码或邮箱");
      }
    } finally {
      setRequestingEmailChange(false);
    }
  };

  const handleConfirmEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailChangeError(null);
    if (!changeEmailToken.trim()) {
      setEmailChangeError("请输入验证 Token");
      return;
    }
    setConfirmingEmailChange(true);
    try {
      await authApi.confirmEmailChange(changeEmailToken.trim());
      await refreshSession();
      setNewEmail("");
      setChangeEmailPassword("");
      setChangeEmailToken("");
      setChangeEmailStep(1);
      showToast("邮箱已成功更新！");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setEmailChangeError(err.message);
      } else {
        setEmailChangeError("确认失败，请确认 Token 是否有效");
      }
    } finally {
      setConfirmingEmailChange(false);
    }
  };

  // -------------------------------------------------------------
  // Change Password State
  // -------------------------------------------------------------
  const [currPassword, setCurrPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [showCurrPassword, setShowCurrPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmNewPassword, setShowConfirmNewPassword] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    if (!currPassword || !newPassword || !confirmNewPassword) {
      setPasswordError("请填写所有密码字段");
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setPasswordError("新密码与确认密码不一致");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError("新密码长度不能少于 8 位");
      return;
    }
    setChangingPassword(true);
    try {
      await authApi.changePassword(currPassword, newPassword);
      setCurrPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      showToast("密码修改成功，其他设备会话已自动下线");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setPasswordError(err.message);
      } else {
        setPasswordError("密码修改失败，请检查当前密码");
      }
    } finally {
      setChangingPassword(false);
    }
  };

  // -------------------------------------------------------------
  // Sessions Management State
  // -------------------------------------------------------------
  const [sessions, setSessions] = useState<AuthSessionItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null);
  const [showLogoutAllModal, setShowLogoutAllModal] = useState(false);
  const [logoutAllPassword, setLogoutAllPassword] = useState("");
  const [showLogoutAllPassword, setShowLogoutAllPassword] = useState(false);
  const [loggingOutAll, setLoggingOutAll] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    setSessionsError(null);
    try {
      const res = await authApi.listSessions();
      setSessions(res.items);
    } catch (err) {
      if (err instanceof AuthApiError) {
        setSessionsError(err.message);
      } else {
        setSessionsError("获取设备会话列表失败");
      }
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    if (activeTab === "sessions" && mode === "authenticated") {
      authApi.listSessions()
        .then((res) => {
          if (mounted) {
            setSessions(res.items);
            setLoadingSessions(false);
          }
        })
        .catch((err) => {
          if (mounted) {
            if (err instanceof AuthApiError) {
              setSessionsError(err.message);
            } else {
              setSessionsError("获取设备会话列表失败");
            }
            setLoadingSessions(false);
          }
        });
    }
    return () => {
      mounted = false;
    };
  }, [activeTab, mode]);

  const handleRevokeDevice = async (deviceItem: AuthSessionItem) => {
    setRevokingSessionId(deviceItem.deviceKey);
    try {
      if (deviceItem.sessionIds && deviceItem.sessionIds.length > 0) {
        await authApi.revokeMany(deviceItem.sessionIds);
      } else {
        await authApi.revokeSession(deviceItem.id);
      }
      await loadSessions();
      showToast("已成功下线该设备");
    } catch (err) {
      if (err instanceof AuthApiError) {
        showToast(err.message, "error");
      } else {
        showToast("下线失败", "error");
      }
    } finally {
      setRevokingSessionId(null);
    }
  };

  const handleLogoutAll = async (e: React.FormEvent) => {
    e.preventDefault();
    setSessionsError(null);
    if (!logoutAllPassword) {
      setSessionsError("请输入当前密码");
      return;
    }
    setLoggingOutAll(true);
    try {
      await authApi.logoutAll(logoutAllPassword);
      setShowLogoutAllModal(false);
      await logout();
      router.push("/login");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setSessionsError(err.message);
      } else {
        setSessionsError("操作失败，请核对密码");
      }
    } finally {
      setLoggingOutAll(false);
    }
  };

  // -------------------------------------------------------------
  // Account Deletion State
  // -------------------------------------------------------------
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [showDeletePassword, setShowDeletePassword] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [cancellingDeletion, setCancellingDeletion] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeleteError(null);
    if (!deletePassword) {
      setDeleteError("请输入当前密码");
      return;
    }
    if (deleteConfirmText !== "DELETE") {
      setDeleteError('请输入大写的 "DELETE" 确认');
      return;
    }
    setDeletingAccount(true);
    try {
      await authApi.deleteAccount(deletePassword, "DELETE");
      await logout();
      router.push("/login");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setDeleteError(err.message);
      } else {
        setDeleteError("注销请求失败，请检查密码");
      }
    } finally {
      setDeletingAccount(false);
    }
  };

  const handleCancelDeletion = async () => {
    setDeleteError(null);
    setCancellingDeletion(true);
    try {
      await authApi.cancelAccountDeletion();
      await refreshSession();
      showToast("已成功撤销注销申请，账号恢复正常");
    } catch (err) {
      if (err instanceof AuthApiError) {
        setDeleteError(err.message);
      } else {
        setDeleteError("撤销失败");
      }
    } finally {
      setCancellingDeletion(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-900 border-t-transparent dark:border-zinc-100 dark:border-t-transparent" />
      </div>
    );
  }

  if (!user) {
    return <div className="p-8 text-center text-sm text-slate-500">未登录</div>;
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          className={`fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-xl px-4 py-3 text-xs font-medium shadow-2xl border animate-in fade-in slide-in-from-bottom-3 duration-300 ${
            toastMessage.type === "success"
              ? "bg-slate-900 text-white dark:bg-zinc-100 dark:text-zinc-900 border-slate-700/50"
              : "bg-red-600 text-white border-red-500"
          }`}
        >
          {toastMessage.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 dark:text-emerald-600" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-white" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-zinc-100">
          账户设置
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">
          管理您的个人信息、安全凭证与设备会话
        </p>
      </div>

      {/* Main Layout: Nav Tabs + Content Area */}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-4">
        {/* Sidebar Nav Tabs */}
        <div className="flex flex-row md:flex-col gap-1 overflow-x-auto pb-2 md:pb-0">
          <button
            onClick={() => setActiveTab("profile")}
            className={`flex items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-xs font-medium transition-colors text-left whitespace-nowrap cursor-pointer ${
              activeTab === "profile"
                ? "bg-slate-100 text-slate-900 dark:bg-zinc-800 dark:text-zinc-100 font-semibold"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200"
            }`}
          >
            <User className="h-4 w-4 shrink-0" />
            <span>基本资料</span>
          </button>

          <button
            onClick={() => {
              setActiveTab("role");
              setSelectedRole(user?.role ?? "student");
            }}
            className={`flex items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-xs font-medium transition-colors text-left whitespace-nowrap cursor-pointer ${
              activeTab === "role"
                ? "bg-slate-100 text-slate-900 dark:bg-zinc-800 dark:text-zinc-100 font-semibold"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200"
            }`}
          >
            <GraduationCap className="h-4 w-4 shrink-0" />
            <span>身份</span>
          </button>

          <button
            onClick={() => setActiveTab("email")}
            className={`flex items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-xs font-medium transition-colors text-left whitespace-nowrap cursor-pointer ${
              activeTab === "email"
                ? "bg-slate-100 text-slate-900 dark:bg-zinc-800 dark:text-zinc-100 font-semibold"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200"
            }`}
          >
            <Mail className="h-4 w-4 shrink-0" />
            <span>邮箱管理</span>
            {!user.emailVerified && (
              <span className="ml-auto inline-block h-2 w-2 rounded-full bg-amber-500" />
            )}
          </button>

          <button
            onClick={() => setActiveTab("password")}
            className={`flex items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-xs font-medium transition-colors text-left whitespace-nowrap cursor-pointer ${
              activeTab === "password"
                ? "bg-slate-100 text-slate-900 dark:bg-zinc-800 dark:text-zinc-100 font-semibold"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200"
            }`}
          >
            <KeyRound className="h-4 w-4 shrink-0" />
            <span>修改密码</span>
          </button>

          <button
            onClick={() => setActiveTab("sessions")}
            className={`flex items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-xs font-medium transition-colors text-left whitespace-nowrap cursor-pointer ${
              activeTab === "sessions"
                ? "bg-slate-100 text-slate-900 dark:bg-zinc-800 dark:text-zinc-100 font-semibold"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200"
            }`}
          >
            <Laptop className="h-4 w-4 shrink-0" />
            <span>登录设备</span>
          </button>

          <div className="pt-2 border-t border-slate-200 dark:border-zinc-800 my-1 hidden md:block" />

          <button
            onClick={() => setActiveTab("danger")}
            className={`flex items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-xs font-medium transition-colors text-left whitespace-nowrap cursor-pointer ${
              activeTab === "danger"
                ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 font-semibold"
                : "text-red-600 hover:bg-red-50/60 dark:text-red-400 dark:hover:bg-red-950/20"
            }`}
          >
            <Trash2 className="h-4 w-4 shrink-0" />
            <span>账号注销</span>
          </button>
        </div>

        {/* Content Section */}
        <div className="md:col-span-3 space-y-6">
          {/* TAB 1: 基本资料 */}
          {activeTab === "profile" && (
            <Card>
              <CardHeader>
                <CardTitle>基本资料</CardTitle>
                <CardDescription>查看您的注册邮箱和公开展示昵称</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {profileError && (
                  <Alert variant="error">
                    <AlertDescription>{profileError}</AlertDescription>
                  </Alert>
                )}

                <div className="flex items-center gap-4 pb-4 border-b border-slate-100 dark:border-zinc-800">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-xl font-bold text-white shadow-sm">
                    {user.displayName ? user.displayName.slice(0, 1).toUpperCase() : "U"}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-slate-900 dark:text-zinc-100">
                        {user.displayName}
                      </h3>
                      {user.emailVerified ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800/50">
                          <ShieldCheck className="h-3 w-3" />
                          邮箱已验证
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border border-amber-200 dark:border-amber-800/50">
                          未验证
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">
                      {user.email}
                    </p>
                  </div>
                </div>

                <form onSubmit={handleUpdateProfile} className="space-y-4 max-w-md">
                  <div>
                    <Label htmlFor="displayName">展示昵称</Label>
                    <Input
                      id="displayName"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="设置您的昵称"
                      maxLength={100}
                      disabled={updatingProfile}
                    />
                  </div>
                  <div>
                    <Label htmlFor="emailDisplay">注册邮箱 (不可直接在此编辑)</Label>
                    <Input
                      id="emailDisplay"
                      value={user.email}
                      disabled
                      className="bg-slate-50 text-slate-500 dark:bg-zinc-800/50 dark:text-zinc-400"
                    />
                    <p className="text-[11px] text-slate-400 dark:text-zinc-500 mt-1">
                      如需更换绑定邮箱，请前往「邮箱管理」分区。
                    </p>
                  </div>
                  <Button type="submit" loading={updatingProfile} disabled={updatingProfile}>
                    保存资料
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}

          {/* TAB: 身份 */}
          {activeTab === "role" && (
            <Card>
              <CardHeader>
                <CardTitle>身份设置</CardTitle>
                <CardDescription>管理您的账户身份类型（学生 / 教师）</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {roleError && (
                  <Alert variant="error">
                    <AlertDescription>{roleError}</AlertDescription>
                  </Alert>
                )}

                <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-900/50">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-xs text-slate-500 dark:text-zinc-400">当前身份</div>
                      <div className="mt-1 flex items-center gap-2">
                        <span className="text-lg font-semibold text-slate-900 dark:text-zinc-100">
                          {currentRole === "teacher" ? "教师" : "学生"}
                        </span>
                        <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-950/50 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50">
                          当前生效
                        </span>
                      </div>
                    </div>
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
                      <GraduationCap className="h-5 w-5" />
                    </div>
                  </div>
                  <p className="mt-3 text-xs text-slate-500 dark:text-zinc-400 border-t border-slate-200/60 pt-3 dark:border-zinc-800/60">
                    说明：切换身份不会影响班级归属与已有数据。
                  </p>
                </div>

                <form onSubmit={handleOpenRoleConfirm} className="space-y-4 max-w-md">
                  <div>
                    <Label className="mb-2 block">切换目标身份</Label>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        type="button"
                        onClick={() => setSelectedRole("student")}
                        disabled={changingRole}
                        className={`flex flex-col items-center justify-center gap-1.5 rounded-xl border p-4 text-center transition-all cursor-pointer ${
                          selectedRole === "student"
                            ? "border-blue-600 bg-blue-50/50 text-blue-700 dark:border-blue-500 dark:bg-blue-950/40 dark:text-blue-300 ring-2 ring-blue-500/20 font-semibold"
                            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800/60"
                        }`}
                      >
                        <GraduationCap className="h-5 w-5" />
                        <span className="text-sm">学生</span>
                        <span className="text-[11px] text-slate-400 dark:text-zinc-500">学习与练习为主</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedRole("teacher")}
                        disabled={changingRole}
                        className={`flex flex-col items-center justify-center gap-1.5 rounded-xl border p-4 text-center transition-all cursor-pointer ${
                          selectedRole === "teacher"
                            ? "border-blue-600 bg-blue-50/50 text-blue-700 dark:border-blue-500 dark:bg-blue-950/40 dark:text-blue-300 ring-2 ring-blue-500/20 font-semibold"
                            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800/60"
                        }`}
                      >
                        <BookOpen className="h-5 w-5" />
                        <span className="text-sm">教师</span>
                        <span className="text-[11px] text-slate-400 dark:text-zinc-500">教学与辅导为主</span>
                      </button>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    loading={changingRole}
                    disabled={changingRole}
                  >
                    保存身份
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}

          {/* TAB 2: 邮箱管理 */}
          {activeTab === "email" && (
            <div className="space-y-6">
              {/* 邮箱验证状态卡片 */}
              <Card>
                <CardHeader>
                  <CardTitle>邮箱验证状态</CardTitle>
                  <CardDescription>验证邮箱以保障账号安全及找回密码</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {verifyError && (
                    <Alert variant="error">
                      <AlertDescription>{verifyError}</AlertDescription>
                    </Alert>
                  )}

                  {user.emailVerified ? (
                    <Alert variant="success" icon={<CheckCircle2 className="h-4 w-4" />}>
                      <AlertTitle>邮箱已完成验证</AlertTitle>
                      <AlertDescription>
                        当前绑定邮箱 <strong>{user.email}</strong> 已通过安全验证，您可以使用它找回密码和接收安全通知。
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <div className="space-y-4">
                      <Alert variant="warning" icon={<AlertTriangle className="h-4 w-4" />}>
                        <AlertTitle>邮箱尚未验证</AlertTitle>
                        <AlertDescription>
                          您的邮箱 <strong>{user.email}</strong> 暂未验证。请发送验证邮件完成校验。
                        </AlertDescription>
                      </Alert>

                      <div className="flex items-center gap-3">
                        <Button
                          variant="secondary"
                          onClick={handleSendVerificationEmail}
                          loading={sendingVerifyEmail}
                          disabled={sendingVerifyEmail}
                        >
                          发送验证邮件
                        </Button>
                      </div>

                      <form onSubmit={handleConfirmVerification} className="space-y-3 pt-2 max-w-md">
                        <div>
                          <Label htmlFor="verifyToken">输入验证 Token</Label>
                          <Input
                            id="verifyToken"
                            value={verifyToken}
                            onChange={(e) => setVerifyToken(e.target.value)}
                            placeholder="输入收到的 Token"
                            disabled={confirmingVerify}
                          />
                          <p className="text-[11px] text-slate-500 dark:text-zinc-400 mt-1.5">
                            提示：开发环境下，验证 Token 会打印在后端日志中（如 <code>docker compose logs backend</code> 或终端输出），直接复制填入即可。
                          </p>
                        </div>
                        <Button type="submit" loading={confirmingVerify} disabled={confirmingVerify}>
                          确认验证
                        </Button>
                      </form>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* 更换邮箱卡片 */}
              <Card>
                <CardHeader>
                  <CardTitle>更换绑定邮箱</CardTitle>
                  <CardDescription>更换您的账号登录与通知邮箱</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {emailChangeError && (
                    <Alert variant="error">
                      <AlertDescription>{emailChangeError}</AlertDescription>
                    </Alert>
                  )}

                  {changeEmailStep === 1 ? (
                    <form onSubmit={handleRequestEmailChange} className="space-y-4 max-w-md">
                      <div>
                        <Label htmlFor="newEmail">新邮箱地址</Label>
                        <Input
                          id="newEmail"
                          type="email"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          placeholder="name@example.com"
                          disabled={requestingEmailChange}
                        />
                      </div>

                      <div>
                        <Label htmlFor="changeEmailPassword">当前账号密码 (安全验证)</Label>
                        <Input
                          id="changeEmailPassword"
                          type={showChangeEmailPassword ? "text" : "password"}
                          value={changeEmailPassword}
                          onChange={(e) => setChangeEmailPassword(e.target.value)}
                          placeholder="输入当前密码"
                          disabled={requestingEmailChange}
                          rightIcon={
                            <button
                              type="button"
                              onClick={() => setShowChangeEmailPassword(!showChangeEmailPassword)}
                              className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                            >
                              {showChangeEmailPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </button>
                          }
                        />
                      </div>

                      <Button type="submit" loading={requestingEmailChange} disabled={requestingEmailChange}>
                        发送换绑请求
                      </Button>
                    </form>
                  ) : (
                    <form onSubmit={handleConfirmEmailChange} className="space-y-4 max-w-md">
                      <Alert variant="info">
                        <AlertDescription>
                          已向新邮箱 <strong>{newEmail}</strong> 发送换绑验证 Token。开发环境下请在后端日志中查看。
                        </AlertDescription>
                      </Alert>

                      <div>
                        <Label htmlFor="changeEmailToken">新邮箱验证 Token</Label>
                        <Input
                          id="changeEmailToken"
                          value={changeEmailToken}
                          onChange={(e) => setChangeEmailToken(e.target.value)}
                          placeholder="输入收到的 Token"
                          disabled={confirmingEmailChange}
                        />
                      </div>

                      <div className="flex items-center gap-3">
                        <Button type="submit" loading={confirmingEmailChange} disabled={confirmingEmailChange}>
                          确认更换邮箱
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setChangeEmailStep(1)}
                          disabled={confirmingEmailChange}
                        >
                          返回上一步
                        </Button>
                      </div>
                    </form>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* TAB 3: 修改密码 */}
          {activeTab === "password" && (
            <Card>
              <CardHeader>
                <CardTitle>修改密码</CardTitle>
                <CardDescription>定期修改高强度密码有助于保障您的账户安全</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {passwordError && (
                  <Alert variant="error">
                    <AlertDescription>{passwordError}</AlertDescription>
                  </Alert>
                )}

                <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
                  <div>
                    <Label htmlFor="currPassword">当前密码</Label>
                    <Input
                      id="currPassword"
                      type={showCurrPassword ? "text" : "password"}
                      value={currPassword}
                      onChange={(e) => setCurrPassword(e.target.value)}
                      placeholder="输入当前使用的密码"
                      disabled={changingPassword}
                      rightIcon={
                        <button
                          type="button"
                          onClick={() => setShowCurrPassword(!showCurrPassword)}
                          className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                        >
                          {showCurrPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      }
                    />
                  </div>

                  <div>
                    <Label htmlFor="newPassword">新密码</Label>
                    <Input
                      id="newPassword"
                      type={showNewPassword ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="至少 8 位，包含字母和数字"
                      disabled={changingPassword}
                      rightIcon={
                        <button
                          type="button"
                          onClick={() => setShowNewPassword(!showNewPassword)}
                          className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                        >
                          {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      }
                    />
                  </div>

                  <div>
                    <Label htmlFor="confirmNewPassword">确认新密码</Label>
                    <Input
                      id="confirmNewPassword"
                      type={showConfirmNewPassword ? "text" : "password"}
                      value={confirmNewPassword}
                      onChange={(e) => setConfirmNewPassword(e.target.value)}
                      placeholder="再次输入新密码"
                      disabled={changingPassword}
                      rightIcon={
                        <button
                          type="button"
                          onClick={() => setShowConfirmNewPassword(!showConfirmNewPassword)}
                          className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                        >
                          {showConfirmNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      }
                    />
                  </div>

                  <p className="text-[11px] text-slate-400 dark:text-zinc-500">
                    修改密码成功后，当前设备会话将保持，其他设备的已登录会话将自动失效退出。
                  </p>

                  <Button type="submit" loading={changingPassword} disabled={changingPassword}>
                    确认修改密码
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}

          {/* TAB 4: 登录设备与会话 */}
          {activeTab === "sessions" && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>登录设备与会话</CardTitle>
                  <CardDescription>管理您账号下所有处于活跃状态的登录设备</CardDescription>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={loadSessions}
                  disabled={loadingSessions}
                  className="gap-1.5"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingSessions ? "animate-spin" : ""}`} />
                  刷新
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                {sessionsError && (
                  <Alert variant="error">
                    <AlertDescription>{sessionsError}</AlertDescription>
                  </Alert>
                )}

                {loadingSessions && sessions.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-400">正在加载会话列表...</div>
                ) : sessions.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-400">暂无活跃会话</div>
                ) : (
                  <div className="divide-y divide-slate-100 dark:divide-zinc-800">
                    {sessions.map((item) => {
                      const ua = item.userAgentLabel?.toLowerCase() || "";
                      const isMobile = ua.includes("mobile") || ua.includes("android") || ua.includes("iphone");

                      return (
                        <div
                          key={item.id}
                          className="flex items-center justify-between py-3.5 first:pt-0 last:pb-0"
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">
                              {isMobile ? <Smartphone className="h-4 w-4" /> : <Laptop className="h-4 w-4" />}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-xs text-slate-900 dark:text-zinc-100">
                                  {item.userAgentLabel || "未知浏览器 / 设备"}
                                </span>
                                {item.current && (
                                  <span className="rounded-md bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800/40">
                                    当前设备
                                  </span>
                                )}
                                {item.sessionCount > 1 && (
                                  <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-zinc-800 dark:text-zinc-300 border border-slate-200 dark:border-zinc-700">
                                    {item.sessionCount} 个会话
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-3 text-[11px] text-slate-400 dark:text-zinc-500 mt-1">
                                <span>首次登录: {new Date(item.createdAt).toLocaleString()}</span>
                                <span>最近活动: {new Date(item.lastSeenAt).toLocaleString()}</span>
                              </div>
                            </div>
                          </div>

                          {!item.current && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleRevokeDevice(item)}
                              loading={revokingSessionId === item.deviceKey}
                              disabled={revokingSessionId !== null}
                            >
                              下线
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
              <CardFooter className="flex justify-between items-center bg-slate-50/50 dark:bg-zinc-800/20 px-6 py-4">
                <p className="text-xs text-slate-500 dark:text-zinc-400">
                  遇到可疑活动？您可以一键下线所有已登录的设备。
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowLogoutAllModal(true)}
                  className="text-red-600 border-red-200 hover:bg-red-50 dark:border-red-900/50 dark:text-red-400 dark:hover:bg-red-950/30"
                >
                  <LogOut className="h-3.5 w-3.5 mr-1.5" />
                  下线所有设备
                </Button>
              </CardFooter>
            </Card>
          )}

          {/* Modal: 下线所有设备二次确认 */}
          {showLogoutAllModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
              <Card className="max-w-md w-full shadow-2xl animate-in fade-in zoom-in-95">
                <CardHeader>
                  <CardTitle>下线所有设备</CardTitle>
                  <CardDescription>
                    为了您的账号安全，执行此操作需要验证当前登录密码。下线后您将被退出到登录页面。
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {sessionsError && (
                    <Alert variant="error" className="mb-4">
                      <AlertDescription>{sessionsError}</AlertDescription>
                    </Alert>
                  )}
                  <form onSubmit={handleLogoutAll} className="space-y-4">
                    <div>
                      <Label htmlFor="logoutAllPassword">当前密码</Label>
                      <Input
                        id="logoutAllPassword"
                        type={showLogoutAllPassword ? "text" : "password"}
                        value={logoutAllPassword}
                        onChange={(e) => setLogoutAllPassword(e.target.value)}
                        placeholder="输入密码以确认"
                        disabled={loggingOutAll}
                        rightIcon={
                          <button
                            type="button"
                            onClick={() => setShowLogoutAllPassword(!showLogoutAllPassword)}
                            className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                          >
                            {showLogoutAllPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        }
                      />
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => {
                          setShowLogoutAllModal(false);
                          setLogoutAllPassword("");
                          setSessionsError(null);
                        }}
                        disabled={loggingOutAll}
                      >
                        取消
                      </Button>
                      <Button type="submit" variant="danger" loading={loggingOutAll} disabled={loggingOutAll}>
                        确认下线全部
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            </div>
          )}

          {/* TAB 5: 账号注销 (Danger Zone) */}
          {activeTab === "danger" && (
            <Card className="border-red-200 dark:border-red-900/60">
              <CardHeader>
                <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                  <AlertTriangle className="h-5 w-5" />
                  <CardTitle>注销账号</CardTitle>
                </div>
                <CardDescription>
                  永久注销您的 Code Navi 账号与所有关联的学习记录、工作区和科研数据
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {deleteError && (
                  <Alert variant="error">
                    <AlertDescription>{deleteError}</AlertDescription>
                  </Alert>
                )}

                {user.status === "pending_deletion" ? (
                  <div className="space-y-4">
                    <Alert variant="warning">
                      <AlertTitle>账号处于待删除保护期</AlertTitle>
                      <AlertDescription>
                        您的账号已提交注销申请。在保护期结束前，您可以随时撤销申请以恢复所有功能。
                      </AlertDescription>
                    </Alert>
                    <Button
                      onClick={handleCancelDeletion}
                      loading={cancellingDeletion}
                      disabled={cancellingDeletion}
                    >
                      撤销注销申请
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="rounded-lg bg-red-50 p-3.5 text-xs text-red-800 dark:bg-red-950/30 dark:text-red-300 leading-relaxed border border-red-100 dark:border-red-900/40">
                      <p className="font-semibold mb-1">注销警告：</p>
                      <ul className="list-disc list-inside space-y-1">
                        <li>注销后，您将无法再使用当前邮箱登录此账号。</li>
                        <li>与该账号关联的所有学习画像、答题记录、科研上下文及代码工作区将进入删除流程。</li>
                        <li>为防止误操作，请在下方输入当前登录密码以及确认文本 <code>DELETE</code>。</li>
                      </ul>
                    </div>

                    <form onSubmit={handleDeleteAccount} className="space-y-4 max-w-md pt-2">
                      <div>
                        <Label htmlFor="deletePassword">当前登录密码</Label>
                        <Input
                          id="deletePassword"
                          type={showDeletePassword ? "text" : "password"}
                          value={deletePassword}
                          onChange={(e) => setDeletePassword(e.target.value)}
                          placeholder="输入当前密码"
                          disabled={deletingAccount}
                          rightIcon={
                            <button
                              type="button"
                              onClick={() => setShowDeletePassword(!showDeletePassword)}
                              className="focus:outline-none hover:text-slate-700 dark:hover:text-zinc-300"
                            >
                              {showDeletePassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </button>
                          }
                        />
                      </div>

                      <div>
                        <Label htmlFor="deleteConfirmText">
                          确认文本（请输入大写 <span className="font-bold text-red-600">DELETE</span>）
                        </Label>
                        <Input
                          id="deleteConfirmText"
                          value={deleteConfirmText}
                          onChange={(e) => setDeleteConfirmText(e.target.value)}
                          placeholder="DELETE"
                          disabled={deletingAccount}
                        />
                      </div>

                      <Button
                        type="submit"
                        variant="danger"
                        loading={deletingAccount}
                        disabled={deletingAccount || deleteConfirmText !== "DELETE"}
                      >
                        确认申请注销
                      </Button>
                    </form>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* 切换身份确认弹窗 */}
      {showRoleConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800">
            <h3 className="text-lg font-bold text-slate-900 dark:text-zinc-100">
              确认切换身份
            </h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-zinc-400 leading-relaxed">
              切换身份仅改变功能入口，不影响班级归属与已有数据。
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowRoleConfirmModal(false)}
                disabled={changingRole}
              >
                取消
              </Button>
              <Button
                type="button"
                onClick={handleConfirmRoleChange}
                loading={changingRole}
                disabled={changingRole}
              >
                确认切换
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
