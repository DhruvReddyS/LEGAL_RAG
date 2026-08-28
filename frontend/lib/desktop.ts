export interface DesktopSystemReadiness {
  platform: string;
  arch: string;
  total_memory_bytes: number;
  available_disk_bytes: number;
  ollama_reachable: boolean;
  ollama_version: string | null;
  installed_models: Array<string | { name: string }>;
  docker_reachable: boolean;
  backend_reachable: boolean;
}

export function isTauriDesktop(): boolean {
  if (typeof window === "undefined") return false;
  return (
    "__TAURI_INTERNALS__" in window ||
    window.location.protocol === "tauri:" ||
    window.location.hostname === "tauri.localhost"
  );
}

export async function invokeDesktop<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(command, args);
}

export function normalizeInstalledModels(
  models: DesktopSystemReadiness["installed_models"],
): string[] {
  return models
    .map((model) => (typeof model === "string" ? model : model.name))
    .filter(Boolean);
}
