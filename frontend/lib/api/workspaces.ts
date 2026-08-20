/** Browser client for the local persistent Workspace orchestration API. */

import { API_BASE } from "@/lib/api/learning";

export type WorkspaceKind = "personal" | "course" | "project" | "research" | "general";
export type TaskStatus = "active" | "paused" | "completed" | "archived";

export interface Workspace {
  id: string;
  title: string;
  kind: WorkspaceKind;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceTask {
  id: string;
  workspace_id: string;
  title: string;
  goal: string;
  success_criteria: string[];
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface WorkspaceActivity {
  id: string;
  workspace_id: string;
  task_id: string | null;
  capability: string;
  action_type: string;
  source_object_type: string;
  source_object_id: string;
  title: string;
  summary: string;
  created_at: string;
}

export class WorkspaceApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "WorkspaceApiError";
  }
}

const PROFILE_STORAGE_KEY = "code-navi:local-profile-id";

/**
 * Return this browser's stable local data scope. It is not an account,
 * credential, or authorization mechanism.
 */
export function getLocalProfileId(): string {
  if (typeof window === "undefined") return "";
  let profileId = window.localStorage.getItem(PROFILE_STORAGE_KEY);
  if (!profileId) {
    profileId = newProfileId();
    window.localStorage.setItem(PROFILE_STORAGE_KEY, profileId);
  }
  return profileId;
}

function newProfileId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes);
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `profile-${hex}`;
  }
  return `profile-${Math.random().toString(36).slice(2, 22)}`;
}

export async function getOrCreatePersonalWorkspace(): Promise<Workspace> {
  const profileId = getLocalProfileId();
  return requestJson<Workspace>(
    `/api/v1/workspaces/personal?local_profile_id=${encodeURIComponent(profileId)}`,
    { method: "POST" },
  );
}

export async function listWorkspaces(limit = 20): Promise<Workspace[]> {
  const profileId = getLocalProfileId();
  const response = await requestJson<{ items: Workspace[] }>(
    `/api/v1/workspaces?local_profile_id=${encodeURIComponent(profileId)}&limit=${limit}`,
  );
  return response.items;
}

export async function createWorkspace(input: {
  title: string;
  kind?: Exclude<WorkspaceKind, "personal">;
  description?: string;
}): Promise<Workspace> {
  return requestJson<Workspace>("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify({ local_profile_id: getLocalProfileId(), ...input }),
  });
}

export async function fetchWorkspace(workspaceId: string): Promise<Workspace> {
  return requestJson<Workspace>(withProfile(`/api/v1/workspaces/${workspaceId}`));
}

export async function createTask(input: {
  goal: string;
  title?: string;
  successCriteria?: string[];
  workspaceId?: string;
}): Promise<WorkspaceTask> {
  return requestJson<WorkspaceTask>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify({
      local_profile_id: getLocalProfileId(),
      goal: input.goal,
      title: input.title,
      success_criteria: input.successCriteria ?? [],
      workspace_id: input.workspaceId,
    }),
  });
}

export async function fetchTask(taskId: string): Promise<WorkspaceTask> {
  return requestJson<WorkspaceTask>(withProfile(`/api/v1/tasks/${taskId}`));
}

export async function listRecentTasks(limit = 8): Promise<WorkspaceTask[]> {
  const response = await requestJson<{ items: WorkspaceTask[] }>(
    withProfile(`/api/v1/tasks/recent?limit=${limit}`),
  );
  return response.items;
}

export async function listWorkspaceTasks(workspaceId: string): Promise<WorkspaceTask[]> {
  const response = await requestJson<{ items: WorkspaceTask[] }>(
    withProfile(`/api/v1/workspaces/${workspaceId}/tasks`),
  );
  return response.items;
}

export async function listWorkspaceActivities(workspaceId: string): Promise<WorkspaceActivity[]> {
  const response = await requestJson<{ items: WorkspaceActivity[] }>(
    withProfile(`/api/v1/workspaces/${workspaceId}/activities`),
  );
  return response.items;
}

export async function listTaskActivities(taskId: string): Promise<WorkspaceActivity[]> {
  const response = await requestJson<{ items: WorkspaceActivity[] }>(
    withProfile(`/api/v1/tasks/${taskId}/activities`),
  );
  return response.items;
}

function withProfile(path: string): string {
  const joiner = path.includes("?") ? "&" : "?";
  return `${path}${joiner}local_profile_id=${encodeURIComponent(getLocalProfileId())}`;
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (networkError) {
    throw new WorkspaceApiError(0, `Network error while contacting ${url}: ${String(networkError)}`);
  }

  if (!response.ok) {
    throw new WorkspaceApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as Record<string, unknown>).detail === "string"
    ) {
      return (body as Record<string, string>).detail;
    }
  } catch {
    // Use the public HTTP status below when an error body is not JSON.
  }
  return response.statusText || `Request failed with status ${response.status}`;
}
