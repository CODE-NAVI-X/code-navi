"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Folder,
  FolderOpen,
  FolderTree,
  Loader2,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import {
  CodeProject,
  CodeProjectFile,
  CodeProjectSymbol,
  fetchCodeProject,
  fetchCodeProjectFile,
  explainCodeProject,
  generateProjectCodeFill,
  ProjectExplanationResponse,
  PracticeApiError,
  uploadCodeProject,
} from "@/lib/api/practice";

const MAX_FILES = 50;
const MAX_PROJECT_BYTES = 2 * 1024 * 1024;

type TreeDirectory = { kind: "directory"; name: string; path: string; children: TreeNode[] };
type TreeFile = { kind: "file"; file: CodeProjectFile };
type TreeNode = TreeDirectory | TreeFile;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function projectTree(files: CodeProjectFile[]): TreeNode[] {
  const root: TreeDirectory = { kind: "directory", name: "", path: "", children: [] };
  const directories = new Map<string, TreeDirectory>([["", root]]);

  for (const file of [...files].sort((left, right) => left.path.localeCompare(right.path))) {
    const segments = file.path.split("/");
    let parent = root;
    let path = "";
    for (const segment of segments.slice(0, -1)) {
      path = path ? `${path}/${segment}` : segment;
      let directory = directories.get(path);
      if (!directory) {
        directory = { kind: "directory", name: segment, path, children: [] };
        directories.set(path, directory);
        parent.children.push(directory);
      }
      parent = directory;
    }
    parent.children.push({ kind: "file", file });
  }
  return root.children;
}

function isAllowedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".py") || name.endsWith(".md");
}

function filePath(file: File): string {
  const relativePath = file.webkitRelativePath || file.name;
  return relativePath.replaceAll("\\", "/").replace(/^\/+/, "");
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取选择的文件"));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("无法读取选择的文件"));
        return;
      }
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

function SymbolList({ symbols }: { symbols: CodeProjectSymbol[] }) {
  if (symbols.length === 0) return null;
  return (
    <ul className="ml-5 border-l border-slate-200 py-1 text-xs dark:border-zinc-800">
      {symbols.map((symbol) => (
        <li key={`${symbol.kind}-${symbol.name}-${symbol.line}`} className="flex items-center gap-1.5 px-2 py-1 text-slate-500 dark:text-zinc-400">
          <span className={symbol.kind === "class" ? "text-amber-600 dark:text-amber-400" : "text-sky-600 dark:text-sky-400"}>
            {symbol.kind === "class" ? "C" : symbol.kind === "method" ? "M" : "F"}
          </span>
          <span className="truncate">{symbol.name}</span>
          <span className="ml-auto text-[10px] text-slate-400">{symbol.line}</span>
        </li>
      ))}
    </ul>
  );
}

function TreeView({
  nodes,
  selectedPath,
  onSelect,
}: {
  nodes: TreeNode[];
  selectedPath: string | null;
  onSelect: (file: CodeProjectFile) => void;
}) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) =>
        node.kind === "directory" ? (
          <DirectoryItem key={node.path} node={node} selectedPath={selectedPath} onSelect={onSelect} />
        ) : (
          <li key={node.file.path}>
            <button
              type="button"
              onClick={() => onSelect(node.file)}
              className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm transition ${
                selectedPath === node.file.path
                  ? "bg-sky-100 text-sky-950 dark:bg-sky-950/60 dark:text-sky-50"
                  : "text-slate-600 hover:bg-slate-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
              }`}
            >
              {node.file.kind === "python" ? <FileCode2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" /> : <FileText className="h-4 w-4 text-violet-600 dark:text-violet-400" />}
              <span className="truncate">{node.file.path.split("/").at(-1)}</span>
            </button>
            <SymbolList symbols={node.file.symbols} />
          </li>
        ),
      )}
    </ul>
  );
}

function DirectoryItem({
  node,
  selectedPath,
  onSelect,
}: {
  node: TreeDirectory;
  selectedPath: string | null;
  onSelect: (file: CodeProjectFile) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-zinc-200 dark:hover:bg-zinc-800"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {open ? <FolderOpen className="h-4 w-4 text-amber-500" /> : <Folder className="h-4 w-4 text-amber-500" />}
        <span className="truncate">{node.name}</span>
      </button>
      {open ? <div className="ml-3 border-l border-slate-200 pl-2 dark:border-zinc-800"><TreeView nodes={node.children} selectedPath={selectedPath} onSelect={onSelect} /></div> : null}
    </li>
  );
}

export default function ProjectCodeNavigationPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project_id");
  const [project, setProject] = useState<CodeProject | null>(null);
  const [selectedFile, setSelectedFile] = useState<CodeProjectFile | null>(null);
  const [content, setContent] = useState<string>("");
  const [projectName, setProjectName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [explanation, setExplanation] = useState<ProjectExplanationResponse | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [generatingPractice, setGeneratingPractice] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    let current = true;
    void fetchCodeProject(projectId)
      .then((loaded) => {
        if (!current) return;
        setProject(loaded);
        setProjectName(loaded.name);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!current) return;
        setError(reason instanceof Error ? reason.message : "无法读取项目结构");
      });
    return () => {
      current = false;
    };
  }, [projectId]);

  const tree = useMemo(() => projectTree(project?.files ?? []), [project]);
  const loading = Boolean(projectId && project?.project_id !== projectId && !error);

  async function selectFile(file: CodeProjectFile) {
    if (!project) return;
    setSelectedFile(file);
    setFileLoading(true);
    setError(null);
    try {
      const response = await fetchCodeProjectFile(project.project_id, file.path);
      setContent(response.content);
      setExplanation(null);
    } catch (reason) {
      setContent("");
      setError(reason instanceof Error ? reason.message : "无法读取项目文件");
    } finally {
      setFileLoading(false);
    }
  }

  async function explainSelectedFile() {
    if (!project || !selectedFile) return;
    setExplaining(true);
    setError(null);
    try {
      setExplanation(await explainCodeProject(project.project_id, { path: selectedFile.path }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法生成项目讲解");
    } finally {
      setExplaining(false);
    }
  }

  async function createFillPractice() {
    if (!project || !selectedFile || selectedFile.kind !== "python") return;
    setGeneratingPractice(true);
    setError(null);
    try {
      const practice = await generateProjectCodeFill(project.project_id, { path: selectedFile.path });
      router.push(`/learning/practice?set_id=${encodeURIComponent(practice.set_id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法生成代码挖空练习");
    } finally {
      setGeneratingPractice(false);
    }
  }

  async function onFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0) return;
    if (files.length > MAX_FILES) {
      setError(`项目最多上传 ${MAX_FILES} 个文件`);
      return;
    }
    if (files.some((file) => !isAllowedFile(file))) {
      setError("项目仅支持 .py 和 .md 文件");
      return;
    }
    const total = files.reduce((sum, file) => sum + file.size, 0);
    if (total > MAX_PROJECT_BYTES) {
      setError("项目总大小不能超过 2 MB");
      return;
    }

    const paths = files.map(filePath);
    if (new Set(paths).size !== paths.length) {
      setError("项目中存在重复文件路径");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadCodeProject({
        name: projectName.trim() || "未命名项目",
        files: await Promise.all(
          files.map(async (file) => ({ path: filePath(file), content_base64: await toBase64(file) })),
        ),
      });
      setProject(uploaded);
      setProjectName(uploaded.name);
      setSelectedFile(null);
      setContent("");
      router.replace(`/learning/projects?project_id=${encodeURIComponent(uploaded.project_id)}`);
    } catch (reason) {
      setError(reason instanceof PracticeApiError ? reason.message : "项目上传失败，请稍后重试");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className={fullscreen ? "fixed inset-0 z-50 overflow-auto bg-[var(--app-surface)]" : "min-h-screen bg-[var(--app-surface)]"}>
      <div className={fullscreen ? "mx-auto flex min-h-screen w-full max-w-none flex-col" : "mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8"}>
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-zinc-800">
          <div className="flex min-w-0 items-center gap-3">
            <Link href="/learning/practice" className="app-button-secondary inline-flex h-9 w-9 items-center justify-center rounded" aria-label="返回动手实践" title="返回动手实践">
              <ChevronRight className="h-4 w-4 rotate-180" />
            </Link>
            <div className="min-w-0">
              <p className="font-mono text-xs font-semibold uppercase text-slate-500 dark:text-zinc-400">Project Navigator</p>
              <h1 className="truncate text-xl font-bold text-slate-950 dark:text-zinc-50">项目代码导航</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setSidebarHidden((value) => !value)} className="app-button-secondary inline-flex h-9 w-9 items-center justify-center rounded" title={sidebarHidden ? "显示项目树" : "收起项目树"}>
              {sidebarHidden ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </button>
            <button type="button" onClick={() => setFullscreen((value) => !value)} className="app-button-secondary inline-flex h-9 w-9 items-center justify-center rounded" title={fullscreen ? "退出全屏" : "全屏查看代码"}>
              {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
          </div>
        </header>

        {!project ? (
          <section className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center py-12">
            <div className="app-card rounded-lg p-6">
              <FolderTree className="h-8 w-8 text-sky-600 dark:text-sky-400" />
              <h2 className="mt-4 text-xl font-bold">上传项目代码</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-zinc-400">选择一个文件夹或多个项目文件，系统只解析 Python 与 Markdown，不执行代码。</p>
              <label className="mt-5 block text-sm font-medium text-slate-700 dark:text-zinc-200">
                项目名称
                <input value={projectName} onChange={(event) => setProjectName(event.target.value)} maxLength={255} placeholder="例如：cnn-image-classifier" className="app-input mt-2 h-10 w-full rounded px-3 text-sm" />
              </label>
              <label className={`app-button-primary mt-4 inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded px-4 py-3 text-sm font-semibold ${uploading ? "pointer-events-none opacity-60" : ""}`}>
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {uploading ? "正在上传与解析" : "选择项目文件"}
                <input type="file" multiple accept=".py,.md,text/x-python,text/markdown" className="hidden" onChange={(event) => void onFilesSelected(event)} />
              </label>
              <p className="mt-3 text-xs leading-5 text-slate-500 dark:text-zinc-400">最多 50 个文件、总计不超过 2 MB。文件夹选择器会保留相对路径；普通多选也可上传。</p>
            </div>
          </section>
        ) : (
          <section className="flex min-h-0 flex-1 flex-col py-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm text-slate-500 dark:text-zinc-400">
              <span className="font-medium text-slate-800 dark:text-zinc-100">{project.name}</span>
              <span>{project.metrics.files ?? project.files.length} 个文件 · {formatBytes(project.metrics.bytes ?? 0)} · {project.metrics.lines ?? 0} 行</span>
            </div>
            <div className={`app-card grid min-h-[62vh] flex-1 overflow-hidden rounded-lg ${sidebarHidden ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-[minmax(240px,320px)_minmax(0,1fr)]"}`}>
              {!sidebarHidden ? <aside className="min-h-0 overflow-auto border-b border-slate-200 p-3 lg:border-b-0 lg:border-r dark:border-zinc-800">
                <p className="mb-2 text-xs font-semibold uppercase text-slate-500 dark:text-zinc-400">资源管理器</p>
                <TreeView nodes={tree} selectedPath={selectedFile?.path ?? null} onSelect={(file) => void selectFile(file)} />
              </aside> : null}
              <article className="flex min-h-0 flex-col bg-slate-950 text-slate-100">
                <div className="flex min-h-11 items-center justify-between border-b border-slate-700 px-4 text-xs text-slate-300">
                  <span className="truncate">{selectedFile?.path ?? "选择左侧文件以查看代码"}</span>
                  {selectedFile ? <div className="flex items-center gap-2"><span>{selectedFile.kind === "python" ? "Python" : "Markdown"}</span><button type="button" onClick={() => void explainSelectedFile()} disabled={explaining} className="inline-flex items-center gap-1 text-sky-300 disabled:opacity-50" title="AI 讲解当前文件">{explaining ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}讲解</button>{selectedFile.kind === "python" ? <button type="button" onClick={() => void createFillPractice()} disabled={generatingPractice} className="text-emerald-300 disabled:opacity-50" title="从当前文件生成关键逻辑挖空练习">{generatingPractice ? "生成中" : "挖空练习"}</button> : null}</div> : null}
                </div>
                {fileLoading ? <div className="flex flex-1 items-center justify-center"><Loader2 className="h-5 w-5 animate-spin" /></div> : selectedFile ? <pre className="min-h-0 flex-1 overflow-auto p-4 font-mono text-sm leading-6"><code>{content}</code></pre> : <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center text-sm text-slate-400"><FileCode2 className="h-8 w-8" /><p>从项目树选择 Python 或 Markdown 文件。</p></div>}
                {explanation ? <section className="max-h-64 overflow-auto border-t border-slate-700 bg-slate-900 p-4 text-sm"><p className="mb-2 text-xs text-slate-400">{explanation.source === "model" ? "模型讲解" : "规则讲解"}</p>{explanation.entries.map((entry) => <div key={`${entry.path}-${entry.symbol ?? "file"}`} className="mb-3 space-y-1"><p className="font-medium text-slate-100">{entry.symbol ?? entry.path}</p>{entry.fact.map((text) => <p key={text} className="text-slate-300">事实：{text}</p>)}{entry.inference.map((text) => <p key={text} className="text-amber-200">推测：{text}</p>)}{entry.to_verify.map((text) => <p key={text} className="text-sky-200">待确认：{text}</p>)}</div>)}</section> : null}
              </article>
            </div>
          </section>
        )}

        {loading ? <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/20"><Loader2 className="h-7 w-7 animate-spin text-slate-900 dark:text-zinc-100" /></div> : null}
        {error ? <div className="app-status-error fixed bottom-5 left-1/2 z-[60] flex max-w-[min(92vw,560px)] -translate-x-1/2 items-start gap-3 rounded px-4 py-3 text-sm shadow-lg" role="alert"><AlertCircle className="mt-0.5 h-4 w-4 flex-none" /><span>{error}</span><button type="button" onClick={() => setError(null)} className="ml-auto" aria-label="关闭错误提示"><X className="h-4 w-4" /></button></div> : null}
      </div>
    </main>
  );
}
