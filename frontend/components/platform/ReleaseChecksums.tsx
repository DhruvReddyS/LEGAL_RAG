"use client";

import { useEffect, useState } from "react";
import { artifactsFor, formatBytes, parseManifest, type Platform, type ReleaseManifest } from "@/lib/release-manifest";
import { RELEASES_URL } from "@/lib/site";

const PLATFORMS: ReadonlyArray<{ id: Platform; label: string; verify: string }> = [
  { id: "macos", label: "macOS", verify: "shasum -a 256 <file>" },
  { id: "windows", label: "Windows", verify: "Get-FileHash <file> -Algorithm SHA256" },
  { id: "linux", label: "Linux", verify: "sha256sum <file>" },
];

/**
 * Reads /releases.json, written from real artifacts at release time. No file
 * means no published build, and the page says that instead of inventing one.
 */
export default function ReleaseChecksums() {
  const [state, setState] = useState<{ status: "loading" | "none" | "ready"; manifest?: ReleaseManifest }>({ status: "loading" });

  useEffect(() => {
    let active = true;
    fetch("/releases.json", { cache: "no-store" })
      .then(response => (response.ok ? response.json() : null))
      .catch(() => null)
      .then(body => {
        if (!active) return;
        const manifest = parseManifest(body);
        setState(manifest ? { status: "ready", manifest } : { status: "none" });
      });
    return () => { active = false; };
  }, []);

  if (state.status === "loading") return <p className="doc-muted" role="status">Looking for published builds&hellip;</p>;
  if (state.status === "none") {
    return (
      <div className="notice-unset" role="status">
        <strong>No build with checksums has been published here yet.</strong>
        <p>
          Older drafts may be listed on the <a href={RELEASES_URL} rel="noopener noreferrer">releases page</a>. Until a
          checksum appears on this page, build from source using the steps below, or treat any download as unverified.
        </p>
      </div>
    );
  }
  const manifest = state.manifest!;
  return (
    <div className="release-groups">
      <p>Version <strong>{manifest.version}</strong>{manifest.published ? `, published ${manifest.published}` : ""}.</p>
      {PLATFORMS.map(platform => {
        const items = artifactsFor(manifest, platform.id);
        return (
          <section key={platform.id} aria-label={platform.label}>
            <h3>{platform.label}</h3>
            {items.length ? (
              <ul className="release-list">
                {items.map(item => (
                  <li key={item.name}>
                    <a href={item.url} rel="noopener noreferrer">{item.name}</a>
                    {item.bytes > 0 && <span className="doc-muted"> {formatBytes(item.bytes)}</span>}
                    <code className="checksum">{item.sha256}</code>
                  </li>
                ))}
              </ul>
            ) : <p className="doc-muted">No {platform.label} build in this release.</p>}
            <p className="doc-muted">Verify with <code>{platform.verify}</code> and compare it to the value above.</p>
          </section>
        );
      })}
    </div>
  );
}
