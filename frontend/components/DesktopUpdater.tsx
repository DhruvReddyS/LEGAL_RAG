"use client";

import { useEffect, useState } from "react";

type UpdateHandle = {
  version: string;
  body?: string;
  downloadAndInstall: (onEvent?: (event: unknown) => void) => Promise<void>;
};

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export default function DesktopUpdater() {
  const [update, setUpdate] = useState<UpdateHandle | null>(null);
  const [status, setStatus] = useState<"idle" | "installing" | "ready" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let active = true;
    const checkForUpdate = async () => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater");
        const available = await check();
        if (active && available) setUpdate(available as UpdateHandle);
      } catch {
        // Development and pre-release builds may intentionally have no updater endpoint.
      }
    };

    void checkForUpdate();
    return () => {
      active = false;
    };
  }, []);

  if (!update || status === "ready") return null;

  const install = async () => {
    setStatus("installing");
    setMessage("Downloading and verifying the signed update…");
    try {
      await update.downloadAndInstall();
      setStatus("ready");
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The update could not be installed.");
    }
  };

  return (
    <aside className="fixed bottom-5 right-5 z-[100] w-[min(390px,calc(100vw-2.5rem))] rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl shadow-slate-950/20">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-sm font-semibold text-white">
          ↑
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-950">Aegis {update.version} is available</p>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {status === "installing"
              ? message
              : status === "error"
                ? message
                : update.body || "Install the verified GitHub Release and restart Aegis."}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              disabled={status === "installing"}
              onClick={() => void install()}
              className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-60"
            >
              {status === "installing" ? "Installing…" : status === "error" ? "Try again" : "Install update"}
            </button>
            {status !== "installing" && (
              <button
                type="button"
                onClick={() => setUpdate(null)}
                className="rounded-lg px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100"
              >
                Later
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
