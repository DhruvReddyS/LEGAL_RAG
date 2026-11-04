"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

const KEY = "corpusil.site-theme";

/**
 * The public pages follow the system theme through CSS alone, so a visitor gets
 * the right colours with no script. This only records an explicit override.
 */
export default function SiteThemeToggle() {
  const [theme, setTheme] = useState<"paper" | "ink" | null>(null);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(KEY);
    } catch {
      // Storage disabled: the system theme stands.
    }
    const active = stored === "ink" || stored === "paper"
      ? stored
      : window.matchMedia("(prefers-color-scheme: dark)").matches ? "ink" : "paper";
    if (stored === "ink" || stored === "paper") document.documentElement.dataset.theme = stored;
    setTheme(active);
  }, []);

  const toggle = () => {
    const next = theme === "ink" ? "paper" : "ink";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // Applies for this page only.
    }
  };

  return (
    <button type="button" className="site-theme" onClick={toggle} aria-label={theme === "ink" ? "Use light theme" : "Use dark theme"}>
      {theme === "ink" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
    </button>
  );
}
