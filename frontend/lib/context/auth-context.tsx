"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { authApi, SessionResponse, AuthUser, AuthApiError, UserRole } from "@/lib/api/auth";

interface AuthContextType {
  mode: "guest" | "authenticated";
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  claimResult: SessionResponse["claimResult"];
  refreshSession: () => Promise<void>;
  login: (email: string, password: string, rememberMe?: boolean, claimGuestData?: boolean) => Promise<void>;
  register: (
    email: string,
    password: string,
    displayName: string,
    claimGuestData?: boolean,
    role?: UserRole
  ) => Promise<void>;
  changeRole: (role: UserRole) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<"guest" | "authenticated">("guest");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [claimResult, setClaimResult] = useState<SessionResponse["claimResult"]>(null);

  const refreshSession = useCallback(async () => {
    try {
      setError(null);
      const res = await authApi.getSession();
      setMode(res.mode);
      setUser(res.user);
      setClaimResult(res.claimResult);
    } catch (err) {
      if (err instanceof AuthApiError) {
        setError(err.message);
      } else {
        setError("获取会话状态失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    authApi
      .getSession()
      .then((res) => {
        if (!mounted) return;
        setMode(res.mode);
        setUser(res.user);
        setClaimResult(res.claimResult);
      })
      .catch((err) => {
        if (!mounted) return;
        if (err instanceof AuthApiError) {
          setError(err.message);
        } else {
          setError("获取会话状态失败");
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const login = async (
    email: string,
    password: string,
    rememberMe = false,
    claimGuestData = true
  ) => {
    setError(null);
    try {
      const res = await authApi.login({
        email,
        password,
        rememberMe,
        claimGuestData,
      });
      setMode(res.mode);
      setUser(res.user);
      setClaimResult(res.claimResult);
    } catch (err) {
      if (err instanceof AuthApiError) {
        setError(err.message);
        throw err;
      }
      setError("登录失败");
      throw err;
    }
  };

  const register = async (
    email: string,
    password: string,
    displayName: string,
    claimGuestData = true,
    role: UserRole = "student"
  ) => {
    setError(null);
    try {
      const res = await authApi.register({
        email,
        password,
        displayName,
        claimGuestData,
        role,
      });
      setMode(res.mode);
      setUser(res.user);
      setClaimResult(res.claimResult);
    } catch (err) {
      if (err instanceof AuthApiError) {
        setError(err.message);
        throw err;
      }
      setError("注册失败");
      throw err;
    }
  };

  const changeRole = async (role: UserRole) => {
    setError(null);
    try {
      await authApi.changeRole(role);
      await refreshSession();
    } catch (err) {
      if (err instanceof AuthApiError) {
        setError(err.message);
        throw err;
      }
      setError("切换身份失败");
      throw err;
    }
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      await refreshSession();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        mode,
        user,
        loading,
        error,
        claimResult,
        refreshSession,
        login,
        register,
        changeRole,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
