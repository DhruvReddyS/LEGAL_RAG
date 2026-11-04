/**
 * F25: when a session cannot be refreshed, the app has to say so. Without this
 * every feature showed an error while the screen looked signed in.
 */
type Listener = () => void;
const listeners = new Set<Listener>();

export function onSessionExpired(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function notifySessionExpired(): void {
  for (const listener of listeners) listener();
}
