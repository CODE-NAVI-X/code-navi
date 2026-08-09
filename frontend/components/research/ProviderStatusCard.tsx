"use client";

import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  PlugZap,
  RefreshCw,
  Save,
  Settings2,
  WifiOff,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  configureResearchProvider,
  getResearchProviderStatus,
  type ProviderConnectionTestResponse,
  type ProviderStatusResponse,
  testResearchProvider,
} from "@/lib/api/research";

type ProviderName = "deepseek" | "openai";

const DEFAULT_MODELS: Record<ProviderName, string> = {
  deepseek: "deepseek-v4-flash",
  openai: "",
};

export function ProviderStatusCard() {
  const [status, setStatus] = useState<ProviderStatusResponse | null>(null);
  const [testResult, setTestResult] = useState<ProviderConnectionTestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [showConfiguration, setShowConfiguration] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [provider, setProvider] = useState<ProviderName>("deepseek");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(DEFAULT_MODELS.deepseek);
  const [baseUrl, setBaseUrl] = useState("https://api.deepseek.com");
  const startedRef = useRef(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextStatus = await getResearchProviderStatus();
      setStatus(nextStatus);
      if (nextStatus.provider === "deepseek" || nextStatus.provider === "openai") {
        setProvider(nextStatus.provider);
        setModel(nextStatus.model || DEFAULT_MODELS[nextStatus.provider]);
      }
      setTestResult(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "无法读取模型状态。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void refresh();
  }, [refresh]);

  async function testConnection() {
    setTesting(true);
    setError(null);
    setSavedMessage(null);
    try {
      setTestResult(await testResearchProvider());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "模型连接测试失败。");
    } finally {
      setTesting(false);
    }
  }

  async function saveAndTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (apiKey.trim().length < 16) {
      setError("API Key 看起来不完整，请粘贴服务商生成的完整 Key。");
      return;
    }
    if (!model.trim()) {
      setError("请填写模型名称。");
      return;
    }
    setSaving(true);
    setTesting(false);
    setError(null);
    setSavedMessage(null);
    setTestResult(null);
    try {
      const nextStatus = await configureResearchProvider({
        provider,
        api_key: apiKey.trim(),
        model: model.trim(),
        base_url: provider === "deepseek" ? baseUrl.trim() || null : null,
      });
      setStatus(nextStatus);
      setApiKey("");
      setShowKey(false);
      setSavedMessage("Key 已安全保存到当前项目的本地配置，正在验证真实连接…");
      setTesting(true);
      const result = await testResearchProvider();
      setTestResult(result);
      setSavedMessage(result.connected ? "配置已保存并连接成功。" : "配置已保存，但连接验证失败。请按下方原因检查。 ");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存模型配置失败。");
    } finally {
      setSaving(false);
      setTesting(false);
    }
  }

  function changeProvider(nextProvider: ProviderName) {
    setProvider(nextProvider);
    setModel(DEFAULT_MODELS[nextProvider]);
    setBaseUrl(nextProvider === "deepseek" ? "https://api.deepseek.com" : "");
    setTestResult(null);
    setSavedMessage(null);
  }

  const configured = status?.configured ?? false;
  const browserConfigurationEnabled = status?.browser_configuration_enabled ?? false;
  const invalidConfiguration = status?.configuration_issue === "invalid_api_key";
  const connectionLabel = invalidConfiguration
    ? "API Key 配置无效"
    : !configured
      ? "配置模型"
      : testResult?.connected
        ? "模型连接正常"
        : testResult
        ? "模型连接失败"
          : browserConfigurationEnabled
            ? "模型已配置（待验证）"
            : "模型已配置（可手动测试）";

  return (
    <details className="group relative">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2.5 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800">
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : invalidConfiguration ? (
          <CircleAlert className="h-3.5 w-3.5 text-rose-500" />
        ) : configured && testResult?.connected ? (
          <PlugZap className="h-3.5 w-3.5 text-emerald-500" />
        ) : configured ? (
          <CircleAlert className="h-3.5 w-3.5 text-amber-500" />
        ) : (
          <KeyRound className="h-3.5 w-3.5 text-sky-600" />
        )}
        <span className="hidden sm:inline">{connectionLabel}</span>
        <ChevronDown className="h-3 w-3 transition group-open:rotate-180" />
      </summary>

      <div className="absolute right-0 z-30 mt-2 max-h-[calc(100vh-7rem)] w-[min(25rem,calc(100vw-1.5rem))] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-xl dark:border-zinc-700 dark:bg-zinc-900">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-700 dark:text-sky-300">Model connection</p>
            <h2 className="mt-1 text-sm font-bold">科研模型连接</h2>
          </div>
          <button type="button" onClick={() => void refresh()} disabled={loading || testing || saving} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-zinc-800" aria-label="刷新模型状态">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {status && (
          <div className={`mt-3 rounded-xl border p-3 text-xs ${configured ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300" : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-300"}`}>
            <p className="flex items-center gap-2 font-semibold">
              {configured ? <CheckCircle2 className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
              {configured ? "已检测到本机配置" : "当前使用基础规则，不是完整 AI Agent"}
            </p>
            <p className="mt-1.5 leading-5">Provider：{status.provider} · Model：{status.model || "未配置"}</p>
          </div>
        )}

        <div className="mt-3 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => setShowConfiguration((value) => !value)} disabled={!browserConfigurationEnabled} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-xs font-semibold hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800">
            <Settings2 className="h-3.5 w-3.5" />
            {browserConfigurationEnabled ? (showConfiguration ? "收起配置" : configured ? "更换 API Key" : "输入 API Key") : "网页配置已禁用"}
          </button>
          <button type="button" onClick={() => void testConnection()} disabled={!configured || testing || saving} className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-3 py-2.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-45 dark:bg-zinc-100 dark:text-zinc-900">
            {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlugZap className="h-3.5 w-3.5" />}
            {testing ? "正在测试…" : "测试连接"}
          </button>
        </div>

        {configured && !browserConfigurationEnabled && (
          <p role="status" className="mt-3 rounded-xl border border-sky-200 bg-sky-50/60 p-3 text-xs leading-5 text-sky-900 dark:border-sky-900/70 dark:bg-sky-950/20 dark:text-sky-200">
            模型配置已从本机运行环境加载。为保护 API Key，网页不能查看或修改 Key；你仍可主动点击“测试连接”验证模型连通性。
          </p>
        )}

        {browserConfigurationEnabled && showConfiguration && (
          <form onSubmit={(event) => void saveAndTest(event)} className="mt-3 space-y-3 rounded-xl border border-sky-200 bg-sky-50/60 p-3 dark:border-sky-900/70 dark:bg-sky-950/20">
            <label className="block text-xs font-semibold">
              服务商
              <select value={provider} onChange={(event) => changeProvider(event.target.value as ProviderName)} disabled={saving || testing} className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-sky-500 dark:border-zinc-700 dark:bg-zinc-950">
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI-compatible</option>
              </select>
            </label>

            <label className="block text-xs font-semibold">
              API Key
              <span className="relative mt-1.5 block">
                <input type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="new-password" spellCheck={false} placeholder="在这里粘贴完整 API Key" disabled={saving || testing} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 pr-10 text-xs outline-none focus:border-sky-500 dark:border-zinc-700 dark:bg-zinc-950" />
                <button type="button" onClick={() => setShowKey((value) => !value)} className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-slate-400 hover:text-slate-700 dark:hover:text-zinc-200" aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}>
                  {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </span>
            </label>

            <label className="block text-xs font-semibold">
              模型名称
              <input value={model} onChange={(event) => setModel(event.target.value)} placeholder={provider === "deepseek" ? "deepseek-v4-flash" : "例如 gpt-5-mini"} disabled={saving || testing} className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-sky-500 dark:border-zinc-700 dark:bg-zinc-950" />
            </label>

            {provider === "deepseek" && (
              <label className="block text-xs font-semibold">
                Base URL
                <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} spellCheck={false} disabled={saving || testing} className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-sky-500 dark:border-zinc-700 dark:bg-zinc-950" />
              </label>
            )}

            <button type="submit" disabled={saving || testing || !apiKey.trim()} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-sky-600 px-3 py-2.5 text-xs font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-45">
              {saving || testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {saving ? "正在安全保存…" : testing ? "正在验证真实连接…" : "保存并测试连接"}
            </button>
            <p className="text-[10px] leading-4 text-slate-500 dark:text-zinc-400">仅允许从本机打开此入口。Key 通过本机接口写入当前项目 Git 已忽略的配置文件，不进入对话、数据库或 localStorage；保存成功后输入框会立即清空。</p>
          </form>
        )}

        {savedMessage && <p className="mt-3 text-xs font-semibold leading-5 text-sky-700 dark:text-sky-300">{savedMessage}</p>}

        {testResult && (
          <div className={`mt-3 rounded-xl border p-3 text-xs leading-5 ${testResult.connected ? "border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-300" : "border-rose-200 text-rose-700 dark:border-rose-900 dark:text-rose-300"}`}>
            <p className="font-semibold">{testResult.message}</p>
            <p>耗时：{testResult.latency_ms} ms</p>
            {testResult.run_id && <p className="break-all font-mono text-[10px]">Run ID：{testResult.run_id}</p>}
          </div>
        )}

        {error && <p role="alert" className="mt-3 text-xs leading-5 text-rose-600 dark:text-rose-300">{error}</p>}
      </div>
    </details>
  );
}
