import { API_BASE } from "@/lib/api/learning";

export interface AuthUser {
  id: string;
  displayName: string;
  email: string;
  emailVerified: boolean;
  status: string;
}

export interface SessionInfo {
  id: string;
  createdAt: string;
  expiresAt: string;
  remembered: boolean;
}

export interface ClaimResult {
  claimed: boolean;
  workspaceCount: number;
  taskCount: number;
  activityCount: number;
}

export interface SessionResponse {
  mode: "guest" | "authenticated";
  user: AuthUser | null;
  session: SessionInfo;
  csrfToken: string;
  claimResult: ClaimResult | null;
}

export interface AuthSessionItem {
  id: string;
  createdAt: string;
  lastSeenAt: string;
  expiresAt: string;
  userAgentLabel: string | null;
  current: boolean;
}

export interface AuthSessionListResponse {
  items: AuthSessionItem[];
}

export class AuthApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly fieldErrors: Record<string, string> = {}
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

let _csrfToken: string | null = null;

export function setStoredCsrfToken(token: string | null): void {
  _csrfToken = token;
}

export function getStoredCsrfToken(): string | null {
  return _csrfToken;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (
    options.method &&
    ["POST", "PUT", "PATCH", "DELETE"].includes(options.method.toUpperCase())
  ) {
    if (_csrfToken) {
      headers["X-CSRF-Token"] = _csrfToken;
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const detail = (data as Record<string, unknown> | null)?.detail;
    if (typeof detail === "object" && detail !== null) {
      const d = detail as Record<string, unknown>;
      throw new AuthApiError(
        response.status,
        typeof d.code === "string" ? d.code : "unknown_error",
        typeof d.message === "string" ? d.message : "请求失败",
        (typeof d.fieldErrors === "object" && d.fieldErrors !== null
          ? d.fieldErrors
          : {}) as Record<string, string>
      );
    }
    throw new AuthApiError(
      response.status,
      "unknown_error",
      typeof detail === "string" ? detail : "请求失败"
    );
  }

  if (
    data &&
    typeof data === "object" &&
    "csrfToken" in data &&
    typeof (data as { csrfToken: unknown }).csrfToken === "string"
  ) {
    setStoredCsrfToken((data as { csrfToken: string }).csrfToken);
  }

  return data as T;
}

export const authApi = {
  getOrCreateGuestSession(): Promise<SessionResponse> {
    return request<SessionResponse>("/api/v1/auth/guest-sessions", {
      method: "POST",
    });
  },

  getSession(): Promise<SessionResponse> {
    return request<SessionResponse>("/api/v1/auth/session", {
      method: "GET",
    });
  },

  register(data: {
    email: string;
    password: string;
    displayName: string;
    claimGuestData?: boolean;
  }): Promise<SessionResponse> {
    return request<SessionResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  login(data: {
    email: string;
    password: string;
    rememberMe?: boolean;
    claimGuestData?: boolean;
  }): Promise<SessionResponse> {
    return request<SessionResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  logout(): Promise<void> {
    return request<void>("/api/v1/auth/logout", {
      method: "POST",
    });
  },

  logoutAll(currentPassword: string): Promise<void> {
    return request<void>("/api/v1/auth/logout-all", {
      method: "POST",
      body: JSON.stringify({ currentPassword }),
    });
  },

  listSessions(): Promise<AuthSessionListResponse> {
    return request<AuthSessionListResponse>("/api/v1/auth/sessions", {
      method: "GET",
    });
  },

  revokeSession(sessionId: string): Promise<void> {
    return request<void>(`/api/v1/auth/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  requestEmailVerification(email?: string): Promise<void> {
    return request<void>("/api/v1/auth/email-verification/request", {
      method: "POST",
      body: JSON.stringify({ email: email || null }),
    });
  },

  confirmEmailVerification(token: string): Promise<void> {
    return request<void>("/api/v1/auth/email-verification/confirm", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  forgotPassword(email: string): Promise<void> {
    return request<void>("/api/v1/auth/password/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  resetPassword(token: string, newPassword: string): Promise<void> {
    return request<void>("/api/v1/auth/password/reset", {
      method: "POST",
      body: JSON.stringify({ token, newPassword }),
    });
  },

  changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return request<void>("/api/v1/auth/password/change", {
      method: "POST",
      body: JSON.stringify({ currentPassword, newPassword }),
    });
  },

  getMe(): Promise<AuthUser> {
    return request<AuthUser>("/api/v1/users/me", {
      method: "GET",
    });
  },

  updateMe(displayName: string): Promise<AuthUser> {
    return request<AuthUser>("/api/v1/users/me", {
      method: "PATCH",
      body: JSON.stringify({ displayName }),
    });
  },

  requestEmailChange(newEmail: string, currentPassword: string): Promise<void> {
    return request<void>("/api/v1/users/me/email-change/request", {
      method: "POST",
      body: JSON.stringify({ newEmail, currentPassword }),
    });
  },

  confirmEmailChange(token: string): Promise<void> {
    return request<void>("/api/v1/users/me/email-change/confirm", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  deleteAccount(currentPassword: string, confirmation: string): Promise<void> {
    return request<void>("/api/v1/users/me", {
      method: "DELETE",
      body: JSON.stringify({ currentPassword, confirmation }),
    });
  },

  cancelAccountDeletion(): Promise<void> {
    return request<void>("/api/v1/users/me/deletion/cancel", {
      method: "POST",
    });
  },
};
