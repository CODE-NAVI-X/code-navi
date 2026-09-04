/** Client for the practice generation gateway (contract §1.2). */

import { getStoredCsrfToken } from "@/lib/api/auth";
import type { PracticeContextV1 } from "@/lib/practice-context";

const API_BASE =
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

export class PracticeApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "PracticeApiError";
    this.status = status;
  }
}

/** §1.1 envelope item as returned by the generate gateway. */
export interface PracticeGatewayItem {
  item_id: string;
  position: number;
  item_kind: string;
  knowledge_points: string[];
  judging: string;
  payload: Record<string, unknown>;
  grading_hint: string | null;
}

export interface PracticeGatewaySetResponse {
  set_id: string;
  kind: string;
  items: PracticeGatewayItem[];
  coverage: string[];
  generation_mode: string;
  provider_name: string;
  effective_context: PracticeContextV1 | null;
  effective_topic: string | null;
}

export interface CodeProjectSymbol {
  kind: "class" | "function" | "method";
  name: string;
  line: number;
  signature: string;
  docstring_summary: string;
}

export interface CodeProjectFile {
  path: string;
  kind: "python" | "markdown";
  size: number;
  symbols: CodeProjectSymbol[];
}

export interface CodeProject {
  project_id: string;
  name: string;
  files: CodeProjectFile[];
  metrics: Record<string, number>;
}

export interface CodeProjectFileContent {
  project_id: string;
  path: string;
  content: string;
  symbols: CodeProjectSymbol[];
}

export interface ProjectExplanationEntry {
  path: string;
  symbol: string | null;
  fact: string[];
  inference: string[];
  to_verify: string[];
}

export interface ProjectExplanationResponse {
  project_id: string;
  entries: ProjectExplanationEntry[];
  source: "model" | "rules";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  const csrf = getStoredCsrfToken();
  if (
    csrf &&
    init?.method &&
    ["POST", "PUT", "PATCH", "DELETE"].includes(init.method.toUpperCase())
  ) {
    headers["X-CSRF-Token"] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(url, { ...init, credentials: "include", headers });
  } catch (networkError) {
    throw new PracticeApiError(0, `无法连接实践服务：${String(networkError)}`);
  }
  if (!response.ok) {
    let detail: string | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : null;
    } catch {
      detail = null;
    }
    throw new PracticeApiError(
      response.status,
      detail ?? `实践服务请求失败（${response.status}）`,
    );
  }
  return (await response.json()) as T;
}

/**
 * Submit the §3.1 context body through the gateway (contract §3.1 boundary:
 * the URL only carries a light pointer; the body goes through ``context``).
 */
export async function generatePracticeSetWithContext(payload: {
  context: PracticeContextV1;
  count?: number;
  difficulty?: "easy" | "medium" | "hard";
}): Promise<PracticeGatewaySetResponse> {
  return request<PracticeGatewaySetResponse>("/api/v1/practice/sets/generate", {
    method: "POST",
    body: JSON.stringify({
      kind: "code_practice",
      count: payload.count ?? 5,
      difficulty: payload.difficulty ?? "medium",
      context: payload.context,
    }),
  });
}

export async function uploadCodeProject(payload: {
  name: string;
  files: Array<{ path: string; content_base64: string }>;
}): Promise<CodeProject> {
  return request<CodeProject>("/api/v1/practice/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCodeProject(projectId: string): Promise<CodeProject> {
  return request<CodeProject>(`/api/v1/practice/projects/${encodeURIComponent(projectId)}`);
}

export async function fetchCodeProjectFile(
  projectId: string,
  path: string,
): Promise<CodeProjectFileContent> {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return request<CodeProjectFileContent>(
    `/api/v1/practice/projects/${encodeURIComponent(projectId)}/files/${encodedPath}`,
  );
}

export async function explainCodeProject(
  projectId: string,
  payload: { path?: string; symbol?: string } = {},
): Promise<ProjectExplanationResponse> {
  return request<ProjectExplanationResponse>(
    `/api/v1/practice/projects/${encodeURIComponent(projectId)}/explain`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function generateProjectCodeFill(
  projectId: string,
  payload: { path: string; symbol?: string; count?: number },
): Promise<PracticeGatewaySetResponse> {
  return request<PracticeGatewaySetResponse>(
    `/api/v1/practice/projects/${encodeURIComponent(projectId)}/code-fill`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
