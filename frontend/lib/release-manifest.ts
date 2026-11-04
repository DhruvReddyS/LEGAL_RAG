/**
 * Build artifacts and their checksums, for the install page.
 *
 * The page reads /releases.json, which scripts/generate_release_manifest.mjs
 * writes from a real release's files. When there is none, the page says so. A
 * checksum nobody computed from a real file is worse than no checksum.
 */

export type Platform = "macos" | "windows" | "linux";

export interface ReleaseArtifact {
  name: string;
  platform: Platform;
  sha256: string;
  bytes: number;
  url: string;
}

export interface ReleaseManifest {
  version: string;
  published: string;
  artifacts: ReleaseArtifact[];
}

const SHA256_RE = /^[0-9a-f]{64}$/;

export function platformOf(filename: string): Platform | null {
  const name = filename.toLowerCase();
  if (name.endsWith(".dmg") || name.endsWith(".app.tar.gz")) return "macos";
  if (name.endsWith(".msi") || name.endsWith(".exe")) return "windows";
  if (name.endsWith(".appimage") || name.endsWith(".deb") || name.endsWith(".rpm")) return "linux";
  return null;
}

/** Everything is checked, because this file decides what people are told to run. */
export function parseManifest(input: unknown): ReleaseManifest | null {
  if (!input || typeof input !== "object") return null;
  const raw = input as Record<string, unknown>;
  if (typeof raw.version !== "string" || !raw.version) return null;
  if (!Array.isArray(raw.artifacts)) return null;
  const artifacts: ReleaseArtifact[] = [];
  for (const item of raw.artifacts as Array<Record<string, unknown>>) {
    if (typeof item?.name !== "string" || typeof item.sha256 !== "string") continue;
    const platform = platformOf(item.name);
    const sha256 = item.sha256.toLowerCase();
    if (!platform || !SHA256_RE.test(sha256)) continue;
    const url = typeof item.url === "string" ? item.url : "";
    if (!url.startsWith("https://")) continue;
    artifacts.push({
      name: item.name,
      platform,
      sha256,
      bytes: typeof item.bytes === "number" && item.bytes > 0 ? item.bytes : 0,
      url,
    });
  }
  if (!artifacts.length) return null;
  return {
    version: raw.version,
    published: typeof raw.published === "string" ? raw.published : "",
    artifacts,
  };
}

export function artifactsFor(manifest: ReleaseManifest | null, platform: Platform): ReleaseArtifact[] {
  return manifest?.artifacts.filter(item => item.platform === platform) ?? [];
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}
