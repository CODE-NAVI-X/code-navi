/** Browser client for persisted cross-module context drafts. */

import type { ResearchConversationResponse } from "./research";

const API_BASE = (
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

export interface ContextSourceObject {
  type: "notebook_item";
  id: string;
}

export interface SelectedContextContent {
  kind: "summary" | "detail";
  label: string;
  content: string;
}

export interface ContextTransfer {
  schema_version: "context-transfer.v1";
  id: string;
  source_module: "learning";
  source_object: ContextSourceObject;
  source_scope_id: string;
  target_module: "research";
  topic: string;
  summary: string;
  selected_content: SelectedContextContent[];
  status: "draft" | "confirmed";
  confirmed_conversation_id: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export class ContextTransferApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ContextTransferApiError";
  }
}

export async function createLearningToResearchContext(
  notebookItemId: string,
  sourceScopeId: string,
): Promise<ContextTransfer> {
  return request<ContextTransfer>("/api/v1/context-transfers", {
    method: "POST",
    body: JSON.stringify({
      source_module: "learning",
      source_object: { type: "notebook_item", id: notebookItemId },
      source_scope_id: sourceScopeId,
      target_module: "research",
      selected_parts: ["summary"],
    }),
  });
}

export async function getContextTransfer(
  transferId: string,
  sourceScopeId: string,
): Promise<ContextTransfer> {
  const params = new URLSearchParams({ source_scope_id: sourceScopeId });
  return request<ContextTransfer>(
    `/api/v1/context-transfers/${encodeURIComponent(transferId)}?${params.toString()}`,
  );
}

export async function updateContextTransfer(
  transferId: string,
  sourceScopeId: string,
  update: {
    topic: string;
    summary: string;
    selected_content: SelectedContextContent[];
  },
): Promise<ContextTransfer> {
  const params = new URLSearchParams({ source_scope_id: sourceScopeId });
  return request<ContextTransfer>(
    `/api/v1/context-transfers/${encodeURIComponent(transferId)}?${params.toString()}`,
    { method: "PATCH", body: JSON.stringify(update) },
  );
}

export async function deleteContextTransfer(
  transferId: string,
  sourceScopeId: string,
): Promise<void> {
  const params = new URLSearchParams({ source_scope_id: sourceScopeId });
  await request<void>(
    `/api/v1/context-transfers/${encodeURIComponent(transferId)}?${params.toString()}`,
    { method: "DELETE" },
  );
}

export async function confirmContextTransfer(
  transferId: string,
  sourceScopeId: string,
  finalContext: {
    topic: string;
    summary: string;
    selected_content: SelectedContextContent[];
  },
): Promise<ResearchConversationResponse> {
  const params = new URLSearchParams({ source_scope_id: sourceScopeId });
  return request<ResearchConversationResponse>(
    `/api/v1/context-transfers/${encodeURIComponent(transferId)}/confirm?${params.toString()}`,
    { method: "POST", body: JSON.stringify(finalContext) },
  );
}

import { getStoredCsrfToken } from "@/lib/api/auth";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  const csrf = getStoredCsrfToken();
  if (csrf && init?.method && ["POST", "PUT", "PATCH", "DELETE"].includes(init.method.toUpperCase())) {
    headers["X-CSRF-Token"] = csrf;
  }

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers,
    });
  } catch (error) {
    throw new ContextTransferApiError(
      0,
      `无法连接上下文传递服务。${error instanceof Error ? ` ${error.message}` : ""}`,
    );
  }
  if (!response.ok) {
    throw new ContextTransferApiError(
      response.status,
      (await errorDetail(response)) ?? `上下文传递请求失败（HTTP ${response.status}）。`,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}
