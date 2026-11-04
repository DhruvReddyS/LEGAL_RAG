/** Keeps /rights usable with no network, once it has been opened once. */
export const RIGHTS_CACHE = "corpusil-rights-v1";

/**
 * A worker does not see what its first page already loaded. So the page hands
 * over its own asset list, or the first offline visit would find no scripts.
 */
export function assetsToCache(resourceNames: string[], origin: string): string[] {
  const urls = new Set<string>(["/rights"]);
  for (const name of resourceNames) {
    try {
      const url = new URL(name);
      if (url.origin === origin && (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/brand/"))) {
        urls.add(url.pathname + url.search);
      }
    } catch { /* not a URL */ }
  }
  return [...urls];
}

export async function keepRightsPageOffline(): Promise<boolean> {
  await navigator.serviceWorker.register("/citizen-offline-sw.js");
  await navigator.serviceWorker.ready;
  const names = performance.getEntriesByType("resource").map(entry => entry.name);
  const cache = await caches.open(RIGHTS_CACHE);
  await cache.addAll(assetsToCache(names, window.location.origin));
  return true;
}
