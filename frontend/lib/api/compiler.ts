/** Client for the online Python compiler API. */

const API_BASE =
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

export interface CompilerRuntimeStatus {
  ready: boolean;
  language: string;
  version: string;
  limits: {
    wallTimeMs: number;
    memoryBytes: number;
    sourceBytes: number;
  };
  message: string;
  ai: {
    status: string;
    message: string;
  };
}

export interface CompilerAssessment {
  category: string;
  severity: string;
  title: string;
  summary: string;
  errorType: string | null;
  line: number | null;
  source: "deterministic_rule";
}

export interface CompilerAiFeedback {
  status: string;
  message?: string;
  evaluationId?: string;
  explanation?: string;
  suggestions?: string[];
  quality?: {
    readability: number;
    structure: number;
    robustness: number;
    overall: number;
  };
  scoreType?: string;
  notice?: string;
}

export interface CompilerRecord {
  id: string;
  createdAt: string;
  category: string;
  title: string;
  summary: string;
  errorType: string | null;
  line: number | null;
  aiStatus: string;
  aiExplanation: string | null;
  suggestions: string[];
  referenceScore: number | null;
  sourceHash: string;
  sourceBytes: number;
  wallTimeMs: number | null;
}

export interface CompilerExecutionResult {
  outcome: string;
  stdout: string;
  stderr: string;
  exitCode: number | null;
  signal: string | null;
  status: string | null;
  metrics: {
    wallTimeMs: number | null;
    cpuTimeMs: number | null;
    memoryBytes: number | null;
  };
  runtime: {
    language: string;
    version: string;
  };
  assessment: CompilerAssessment;
  ai: CompilerAiFeedback;
  record: CompilerRecord | { status: "unavailable" } | null;
  serviceTiming: Record<string, number>;
}

export interface CompilerTestResult {
  testId?: string;
  index: number;
  status: string;
  points: number;
  hidden: boolean;
  stdout: string | null;
  stderr: string | null;
  errorType: string | null;
}

export interface CompilerJudgeResult {
  submissionId: string;
  problemId: string;
  problemVersion: number;
  verdict: string;
  score: number;
  passed: number;
  total: number;
  passedPoints: number;
  totalPoints: number;
  testResults: CompilerTestResult[];
}

export interface CompilerGuidance {
  reply: string;
  strategy: "question" | "hint" | "explanation";
  blocked: boolean;
}

export class CompilerApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "CompilerApiError";
  }
}

export async function fetchCompilerRuntime(): Promise<CompilerRuntimeStatus> {
  return request<CompilerRuntimeStatus>("/api/v1/compiler/runtime");
}

export async function executePython(payload: {
  source: string;
  stdin: string;
  learnerId: string;
  enableAi: boolean;
}): Promise<CompilerExecutionResult> {
  return request<CompilerExecutionResult>("/api/v1/compiler/execute", {
    method: "POST",
    body: JSON.stringify({
      language: "python",
      source: payload.source,
      stdin: payload.stdin,
      learnerId: payload.learnerId,
      enableAi: payload.enableAi,
    }),
  });
}

export async function evaluatePythonRun(payload: {
  evaluationId: string;
  learnerId: string;
}): Promise<{ ai: CompilerAiFeedback; record: CompilerRecord | null }> {
  return request<{ ai: CompilerAiFeedback; record: CompilerRecord | null }>(
    "/api/v1/compiler/evaluate",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function submitPython(payload: {
  problemId: string;
  problemVersion?: number;
  source: string;
  learnerId: string;
}): Promise<CompilerJudgeResult> {
  return request<CompilerJudgeResult>("/api/v1/compiler/submit", {
    method: "POST",
    body: JSON.stringify({ ...payload, problemVersion: payload.problemVersion ?? 1 }),
  });
}

export async function requestCompilerGuidance(payload: {
  submissionId: string;
  message: string;
  learnerId: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
}): Promise<{ submissionId: string; ai: CompilerGuidance }> {
  return request<{ submissionId: string; ai: CompilerGuidance }>("/api/v1/compiler/guidance", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCompilerRecords(
  learnerId: string,
): Promise<CompilerRecord[]> {
  const response = await request<{ records: CompilerRecord[] }>(
    `/api/v1/compiler/records?learnerId=${encodeURIComponent(learnerId)}`,
  );
  return response.records;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (error) {
    throw new CompilerApiError(0, `无法连接在线编译服务：${String(error)}`);
  }

  if (!response.ok) {
    throw new CompilerApiError(
      response.status,
      (await errorDetail(response)) ?? `在线编译服务请求失败（${response.status}）`,
    );
  }

  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const payload = body as { detail?: unknown; error?: unknown };
      if (typeof payload.detail === "string") return payload.detail;
      if (typeof payload.error === "string") return payload.error;
    }
  } catch {
    // Keep status fallback for proxy or server errors that are not JSON.
  }
  return response.statusText || null;
}

