import { API_BASE } from "@/lib/api/learning";
import { getStoredCsrfToken } from "@/lib/api/auth";

export interface ClassroomItem {
  id: string;
  name: string;
  inviteCode: string | null;
  roleInClass: "teacher" | "student" | string;
  isOwner: boolean;
  memberCount: number;
  createdAt: string;
}

export interface ClassroomMember {
  userId: string;
  displayName: string;
  roleInClass: "teacher" | "student" | string;
  joinedAt: string;
}

export class ClassApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string
  ) {
    super(message);
    this.name = "ClassApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrf = getStoredCsrfToken();
    if (csrf) {
      headers["X-CSRF-Token"] = csrf;
    }
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 12000);

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === "AbortError") {
      throw new ClassApiError(0, "network.timeout", "网络请求超时，请检查网络连接");
    }
    throw new ClassApiError(0, "network.failed", "网络请求失败，请稍后重试");
  } finally {
    clearTimeout(timeoutId);
  }

  const text = await response.text();
  let data: Record<string, unknown> | null = null;
  if (text) {
    try {
      data = JSON.parse(text) as Record<string, unknown>;
    } catch {
      data = { message: text };
    }
  }

  if (!response.ok) {
    const detail = data?.detail;
    let code = "class.error";
    let message = "班级操作失败";

    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object" && detail !== null) {
      const detailObj = detail as Record<string, unknown>;
      if (typeof detailObj.code === "string") {
        code = detailObj.code;
      }
      if (typeof detailObj.message === "string") {
        message = detailObj.message;
      }
    }
    throw new ClassApiError(response.status, code, message);
  }

  return data as unknown as T;
}

export async function listClasses(): Promise<ClassroomItem[]> {
  const res = await request<{ items: ClassroomItem[] }>("/api/v1/classes");
  return res.items;
}

export async function getClassroom(classId: string): Promise<ClassroomItem> {
  return request<ClassroomItem>(`/api/v1/classes/${classId}`);
}

export async function createClass(name: string): Promise<ClassroomItem> {
  return request<ClassroomItem>("/api/v1/classes", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function joinClass(inviteCode: string): Promise<ClassroomItem> {
  return request<ClassroomItem>("/api/v1/classes/join", {
    method: "POST",
    body: JSON.stringify({ inviteCode }),
  });
}

export async function getClassMembers(classId: string): Promise<ClassroomMember[]> {
  const res = await request<{ items: ClassroomMember[] }>(`/api/v1/classes/${classId}/members`);
  return res.items;
}
