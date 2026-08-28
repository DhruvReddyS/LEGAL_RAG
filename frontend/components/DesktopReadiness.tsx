"use client";

import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clipboard,
  Cpu,
  Database,
  Download,
  ExternalLink,
  HardDrive,
  Laptop,
  Loader2,
  MemoryStick,
  RefreshCw,
  Server,
  Sparkles,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DesktopSystemReadiness,
  invokeDesktop,
  isTauriDesktop,
  normalizeInstalledModels,
} from "@/lib/desktop";

const SEEN_KEY = "aegis.desktop.readiness.seen.v1";
const DEFAULT_MODEL = "qwen3-14b-16k:latest";
const START_COMMAND = "docker compose --env-file .env -f docker/docker-compose.yml up -d";

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "Unavailable";
  return `${(value / 1024 ** 3).toFixed(value >= 100 * 1024 ** 3 ? 0 : 1)} GB`;
}

function errorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return "The desktop readiness check could not be completed.";
}

function StatusDot({ ready }: { ready: boolean }) {
  return (
    <span
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
        ready ? "bg-[#e9f8ef] text-[#16825d]" : "bg-[#fff4ed] text-[#b54708]"
      }`}
    >
      {ready ? <Check size={14} strokeWidth={2.5} /> : <AlertTriangle size={14} />}
    </span>
  );
}

export default function DesktopReadiness() {
  const [desktop, setDesktop] = useState(false);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [modelInstallerOpen, setModelInstallerOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [readiness, setReadiness] = useState<DesktopSystemReadiness | null>(null);

  const models = useMemo(
    () => normalizeInstalledModels(readiness?.installed_models ?? []),
    [readiness?.installed_models],
  );
  const ready = Boolean(
    readiness?.ollama_reachable && readiness.backend_reachable && models.length,
  );
  const healthyCount = readiness
    ? [readiness.ollama_reachable, readiness.backend_reachable, readiness.docker_reachable].filter(Boolean).length
    : 0;

  const refresh = useCallback(async (showLoader = true) => {
    if (!isTauriDesktop()) return;
    if (showLoader) setLoading(true);
    setError("");
    try {
      const result = await invokeDesktop<DesktopSystemReadiness>("get_system_readiness");
      setReadiness(result);
      const alreadySeen = window.localStorage.getItem(SEEN_KEY) === "true";
      if (!alreadySeen || !result.ollama_reachable || !result.backend_reachable || !result.installed_models.length) {
        setOpen(true);
      }
    } catch (nextError) {
      setError(errorMessage(nextError));
      setOpen(true);
    } finally {
      if (showLoader) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const active = isTauriDesktop();
    setDesktop(active);
    if (active) void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!desktop) return;
    const interval = window.setInterval(() => void refresh(false), 30_000);
    return () => window.clearInterval(interval);
  }, [desktop, refresh]);

  const pullModel = async () => {
    const selected = model.trim();
    if (!selected || pulling) return;
    setPulling(true);
    setError("");
    try {
      await invokeDesktop("pull_ollama_model", { model: selected });
      await refresh(false);
    } catch (nextError) {
      setError(errorMessage(nextError));
    } finally {
      setPulling(false);
    }
  };

  const openOllamaDownload = async () => {
    setError("");
    try {
      await invokeDesktop("open_ollama_download");
    } catch (nextError) {
      setError(errorMessage(nextError));
    }
  };

  const copyStartCommand = async () => {
    await navigator.clipboard.writeText(START_COMMAND);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const dismiss = () => {
    if (ready) window.localStorage.setItem(SEEN_KEY, "true");
    setOpen(false);
  };

  if (!desktop) return null;

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-[70] flex items-center gap-2 rounded-full border border-[#d0d5dd] bg-white px-3.5 py-2 text-xs font-semibold text-[#344054] shadow-[0_10px_30px_rgba(16,24,40,.14)] transition hover:-translate-y-0.5 hover:border-[#aab5c2]"
          aria-label="Open desktop system readiness"
        >
          <span className={`h-2 w-2 rounded-full ${ready ? "bg-[#20a36b]" : "bg-[#e5822c]"}`} />
          Local AI {ready ? "ready" : "needs attention"}
        </button>
      )}

      {open && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-[#07111f]/70 px-4 py-8 backdrop-blur-sm">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="desktop-readiness-title"
            className="relative w-full max-w-[940px] overflow-hidden rounded-[26px] border border-white/15 bg-[#f7f9fb] shadow-[0_32px_100px_rgba(3,12,25,.45)]"
          >
            <div className="relative overflow-hidden bg-[#0b1729] px-6 py-6 text-white md:px-8 md:py-7">
              <div className="absolute inset-0 opacity-40 [background-image:radial-gradient(circle_at_85%_10%,rgba(80,190,198,.35),transparent_28%)]" />
              <div className="relative flex items-start justify-between gap-5">
                <div className="flex items-start gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/10 text-[#8ed4d9]"><Laptop size={23} /></span>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#8ed4d9]">Private desktop runtime</p>
                    <h2 id="desktop-readiness-title" className="mt-1.5 text-2xl font-semibold tracking-[-.03em]">Prepare your local AI workspace</h2>
                    <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-400">Aegis sends legal prompts to the backend on this device. The backend retrieves verified sources, then uses your local Ollama model for grounded generation.</p>
                  </div>
                </div>
                <button onClick={dismiss} className="rounded-xl p-2 text-slate-400 transition hover:bg-white/10 hover:text-white" aria-label="Close readiness window"><X size={18} /></button>
              </div>
            </div>

            <div className="p-5 md:p-7">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-[#1d2939]">System readiness</p>
                  <p className="mt-1 text-xs text-[#667085]">{loading ? "Checking local services…" : readiness ? `${healthyCount}/3 runtime services detected` : "Waiting for system information"}</p>
                </div>
                <button onClick={() => void refresh()} disabled={loading || pulling} className="button-secondary h-10 text-xs">
                  <RefreshCw size={14} className={loading ? "animate-spin" : ""} />Check again
                </button>
              </div>

              {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-[#fecdca] bg-[#fef3f2] px-4 py-3 text-xs leading-5 text-[#b42318]"><AlertTriangle size={15} className="mt-0.5 shrink-0" /><span>{error}</span></div>}

              <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4"><div className="flex items-center justify-between"><Cpu size={17} className="text-[#167184]" /><span className="text-[9px] font-semibold uppercase tracking-wider text-[#98a2b3]">Device</span></div><p className="mt-4 text-sm font-semibold capitalize text-[#344054]">{readiness?.platform ?? "Detecting…"}</p><p className="mt-1 text-xs text-[#98a2b3]">{readiness?.arch ?? "Architecture"}</p></div>
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4"><div className="flex items-center justify-between"><MemoryStick size={17} className="text-[#76512f]" /><span className="text-[9px] font-semibold uppercase tracking-wider text-[#98a2b3]">Memory</span></div><p className="mt-4 text-sm font-semibold text-[#344054]">{formatBytes(readiness?.total_memory_bytes ?? 0)}</p><p className="mt-1 text-xs text-[#98a2b3]">Total system RAM</p></div>
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4"><div className="flex items-center justify-between"><HardDrive size={17} className="text-[#6554a3]" /><span className="text-[9px] font-semibold uppercase tracking-wider text-[#98a2b3]">Storage</span></div><p className="mt-4 text-sm font-semibold text-[#344054]">{formatBytes(readiness?.available_disk_bytes ?? 0)}</p><p className="mt-1 text-xs text-[#98a2b3]">Available for models</p></div>
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4"><div className="flex items-center justify-between"><Database size={17} className="text-[#245b9e]" /><span className="text-[9px] font-semibold uppercase tracking-wider text-[#98a2b3]">Models</span></div><p className="mt-4 text-sm font-semibold text-[#344054]">{models.length || "None"}</p><p className="mt-1 truncate text-xs text-[#98a2b3]" title={models.join(", ")}>{models[0] ?? "Install one below"}</p></div>
              </div>

              <div className="mt-5 grid gap-3 lg:grid-cols-3">
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4">
                  <div className="flex items-start gap-3"><StatusDot ready={Boolean(readiness?.ollama_reachable)} /><div className="min-w-0"><p className="text-sm font-semibold text-[#344054]">Ollama model runtime</p><p className="mt-1 text-xs text-[#667085]">{readiness?.ollama_reachable ? `Connected${readiness.ollama_version ? ` · ${readiness.ollama_version}` : ""}` : "Required for private local generation"}</p></div></div>
                  {!readiness?.ollama_reachable && <button onClick={openOllamaDownload} className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-[#167184]">Download Ollama <ExternalLink size={12} /></button>}
                </div>
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4">
                  <div className="flex items-start gap-3"><StatusDot ready={Boolean(readiness?.docker_reachable)} /><div><p className="text-sm font-semibold text-[#344054]">Docker engine</p><p className="mt-1 text-xs text-[#667085]">{readiness?.docker_reachable ? "Available for the Aegis service stack" : "Open Docker Desktop before starting services"}</p></div></div>
                </div>
                <div className="rounded-2xl border border-[#e4e7ec] bg-white p-4">
                  <div className="flex items-start gap-3"><StatusDot ready={Boolean(readiness?.backend_reachable)} /><div><p className="text-sm font-semibold text-[#344054]">Aegis backend</p><p className="mt-1 text-xs text-[#667085]">{readiness?.backend_reachable ? "API, retrieval and authentication online" : "Start the local Docker services"}</p></div></div>
                  {!readiness?.backend_reachable && <button onClick={copyStartCommand} className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-[#167184]">{copied ? <Check size={12} /> : <Clipboard size={12} />}{copied ? "Command copied" : "Copy start command"}</button>}
                </div>
              </div>

              {readiness?.ollama_reachable && (models.length === 0 || modelInstallerOpen) && (
                <div className="mt-5 rounded-2xl border border-[#c9dfe2] bg-[#f2fafb] p-5">
                  <div className="flex items-start gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-[#167184] shadow-sm"><Download size={17} /></span><div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold text-[#244b53]">Install a local legal reasoning model</p><p className="mt-1 text-xs leading-5 text-[#53747a]">The recommended model matches this project’s default backend profile. Download time depends on your connection and the model may require substantial disk space.</p></div>{models.length > 0 && <button onClick={() => setModelInstallerOpen(false)} aria-label="Close model installer" className="rounded-lg p-1.5 text-[#789197] hover:bg-white"><X size={14} /></button>}</div></div></div>
                  <div className="mt-4 flex flex-col gap-2 sm:flex-row"><input value={model} onChange={(event) => setModel(event.target.value)} disabled={pulling} aria-label="Ollama model name" className="field h-10 flex-1 bg-white" /><button onClick={pullModel} disabled={pulling || !model.trim()} className="button-primary h-10 whitespace-nowrap text-xs">{pulling ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}{pulling ? "Downloading model…" : "Install model"}</button></div>
                </div>
              )}

              {models.length > 0 && (
                <div className="mt-5 rounded-2xl border border-[#d7eadf] bg-[#f3faf6] p-4">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div className="flex min-w-0 items-start gap-3"><CheckCircle2 size={18} className="mt-0.5 shrink-0 text-[#16825d]" /><div className="min-w-0"><p className="text-sm font-semibold text-[#245a42]">Local model available</p><div className="mt-2 flex flex-wrap gap-2">{models.map((item) => <span key={item} className="rounded-full border border-[#cde5d7] bg-white px-2.5 py-1 text-[10px] font-medium text-[#35664f]">{item}</span>)}</div></div></div>{!modelInstallerOpen && <button onClick={() => setModelInstallerOpen(true)} className="shrink-0 text-xs font-semibold text-[#167184]">Install another model</button>}</div>
                </div>
              )}

              <div className="mt-6 flex flex-col-reverse items-stretch justify-between gap-3 border-t border-[#e4e7ec] pt-5 sm:flex-row sm:items-center">
                <p className="flex items-center gap-2 text-[11px] text-[#667085]"><CircleDot size={12} className="text-[#20a36b]" />No prompts or evidence are sent to a cloud LLM.</p>
                <button onClick={dismiss} disabled={!ready} className="button-primary h-11 px-5 disabled:opacity-50">
                  {ready ? <><Sparkles size={15} />Enter Aegis<ChevronRight size={14} /></> : <><Server size={15} />Complete required setup</>}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
