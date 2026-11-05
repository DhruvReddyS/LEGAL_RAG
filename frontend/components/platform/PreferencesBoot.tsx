"use client";

import { useEffect } from "react";
import { applyPreferences, readPreferences, readTheme } from "@/lib/preferences";

/**
 * Applies reading preferences on every page. A script tag in the head would
 * apply them sooner, but the desktop app's content policy forbids inline script,
 * and a moment at standard size is a fair price for one policy everywhere.
 */
export default function PreferencesBoot() {
  useEffect(() => { applyPreferences(readPreferences()); document.documentElement.dataset.theme = readTheme(); }, []);
  return null;
}
