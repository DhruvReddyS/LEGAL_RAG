"use client";
import { useEffect, useSyncExternalStore } from "react";
import { getLang, subscribeLang, t as translate, type UiKey } from "@/lib/citizen-i18n";
import type { Lang } from "@/lib/citizen-law/law";

const serverLang = (): Lang => "en";

/** The citizen's language. English on the first paint, then the saved choice. */
export function useCitizenLang(active = true): { lang: Lang; t: (key: UiKey) => string } {
  const stored = useSyncExternalStore(subscribeLang, getLang, serverLang);
  // Professional screens are not translated, so they ignore a choice left in this browser.
  const lang = active ? stored : "en";
  useEffect(() => {
    if (!active) return;
    document.documentElement.lang = lang;
    return () => { document.documentElement.lang = "en"; };
  }, [active, lang]);
  return { lang, t: (key: UiKey) => translate(key, lang) };
}
