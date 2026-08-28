import { isTauriDesktop } from "@/lib/desktop";

const STORAGE_KEY = "aegis.desktop.backend-base-url.v1";
export const DEFAULT_BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface BackendConnectionProbe {
  url: string;
  reachable: boolean;
  status: string | null;
  latencyMs: number | null;
  error: string | null;
}

export function validateBackendBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("Enter a complete backend URL, for example https://aegis-device.example.ts.net");
  }

  if (parsed.username || parsed.password) {
    throw new Error("Do not place usernames, passwords or tokens in the backend URL.");
  }
  if (parsed.search || parsed.hash) {
    throw new Error("The backend URL cannot contain query parameters or a fragment.");
  }
  if (parsed.pathname !== "/") {
    throw new Error("Enter the backend origin only, without /health or another path.");
  }

  const local = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1" || parsed.hostname === "[::1]";
  if (parsed.protocol !== "https:" && !(local && parsed.protocol === "http:")) {
    throw new Error("Remote backends must use HTTPS. HTTP is accepted only for this device.");
  }

  return parsed.origin;
}

export function isLocalBackendUrl(value: string): boolean {
  try {
    const hostname = new URL(validateBackendBaseUrl(value)).hostname;
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
  } catch {
    return false;
  }
}

export function getRuntimeBackendUrl(): string {
  if (typeof window === "undefined" || !isTauriDesktop()) return DEFAULT_BACKEND_URL;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (!stored) return DEFAULT_BACKEND_URL;
  try {
    return validateBackendBaseUrl(stored);
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return DEFAULT_BACKEND_URL;
  }
}

export function saveRuntimeBackendUrl(value: string): string {
  const validated = validateBackendBaseUrl(value);
  window.localStorage.setItem(STORAGE_KEY, validated);
  return validated;
}

export function resetRuntimeBackendUrl(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

export function hasRuntimeBackendOverride(): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem(STORAGE_KEY) !== null;
}

export async function probeBackendConnection(
  value: string,
  timeoutMs = 8_000,
): Promise<BackendConnectionProbe> {
  let url: string;
  try {
    url = validateBackendBaseUrl(value);
  } catch (error) {
    return {
      url: value.trim(),
      reachable: false,
      status: null,
      latencyMs: null,
      error: error instanceof Error ? error.message : "Invalid backend URL.",
    };
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const started = performance.now();
  try {
    const response = await fetch(`${url}/health`, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    });
    const latencyMs = Math.round(performance.now() - started);
    if (!response.ok) {
      return { url, reachable: false, status: null, latencyMs, error: `Health check returned HTTP ${response.status}.` };
    }
    let status = "online";
    try {
      const body = await response.json() as { status?: string };
      status = body.status ?? status;
    } catch {
      // A successful health response without JSON is still reachable.
    }
    return { url, reachable: true, status, latencyMs, error: null };
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    return {
      url,
      reachable: false,
      status: null,
      latencyMs: null,
      error: timedOut
        ? "Connection timed out. Confirm the private network and backend are running."
        : "Could not reach /health. Check the URL, HTTPS certificate, private network and backend CORS settings.",
    };
  } finally {
    window.clearTimeout(timeout);
  }
}
