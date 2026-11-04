/**
 * Reading preferences for this device: text size and low-bandwidth mode.
 *
 * Per device, because a phone on a poor connection and a desktop on office fibre
 * want different things from the same account.
 */

export type TextSize = "standard" | "large" | "larger";

export interface ReadingPreferences {
  textSize: TextSize;
  lowBandwidth: boolean;
}

export const TEXT_SIZES: ReadonlyArray<{ value: TextSize; label: string; scale: number }> = [
  { value: "standard", label: "Standard", scale: 1 },
  { value: "large", label: "Large", scale: 1.15 },
  { value: "larger", label: "Larger", scale: 1.3 },
];

export const PREFERENCES_KEY = "corpusil.reading.v1";
export const PREFERENCES_EVENT = "corpusil:reading-preferences";

export function parsePreferences(raw: string | null, saveData = false): ReadingPreferences {
  // The browser's data-saver setting is the starting point, not an override.
  const fallback: ReadingPreferences = { textSize: "standard", lowBandwidth: saveData };
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw) as Partial<ReadingPreferences>;
    return {
      textSize: TEXT_SIZES.some(item => item.value === parsed.textSize)
        ? (parsed.textSize as TextSize)
        : "standard",
      lowBandwidth: typeof parsed.lowBandwidth === "boolean" ? parsed.lowBandwidth : saveData,
    };
  } catch {
    return fallback;
  }
}

export function scaleFor(size: TextSize): number {
  return TEXT_SIZES.find(item => item.value === size)?.scale ?? 1;
}

/** What each page does differently in low-bandwidth mode. One place, so it is tested. */
export function bandwidthPlan(lowBandwidth: boolean) {
  return lowBandwidth
    ? { historyPageSize: 15, pollCorpusStatus: false, pollIntervalMs: 4000 }
    : { historyPageSize: 30, pollCorpusStatus: true, pollIntervalMs: 1500 };
}

export function readPreferences(): ReadingPreferences {
  if (typeof window === "undefined") return parsePreferences(null);
  const saveData = Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
  try {
    return parsePreferences(window.localStorage.getItem(PREFERENCES_KEY), saveData);
  } catch {
    return parsePreferences(null, saveData);
  }
}

export function applyPreferences(preferences: ReadingPreferences, root: HTMLElement = document.documentElement): void {
  root.dataset.textSize = preferences.textSize;
  root.dataset.lowBandwidth = preferences.lowBandwidth ? "on" : "off";
  root.style.setProperty("--reading-scale", String(scaleFor(preferences.textSize)));
}

export function savePreferences(preferences: ReadingPreferences): void {
  try {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    // Still applied for this page.
  }
  applyPreferences(preferences);
  window.dispatchEvent(new CustomEvent(PREFERENCES_EVENT));
}
