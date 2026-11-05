"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { readTheme, saveTheme } from "@/lib/preferences";

/** The public pages follow the system theme until someone chooses. */
export default function SiteThemeToggle() {
  const [theme, setTheme] = useState<"paper" | "ink" | null>(null);

  useEffect(() => { setTheme(readTheme()); }, []);

  const toggle = () => {
    const next = theme === "ink" ? "paper" : "ink";
    setTheme(next);
    saveTheme(next);
  };

  return (
    <button type="button" className="site-theme" onClick={toggle} aria-label={theme === "ink" ? "Use light theme" : "Use dark theme"}>
      {theme === "ink" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
    </button>
  );
}
