"use client";
import { Languages, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { translateAnswer } from "@/lib/api-citizen";
import type { Lang } from "@/lib/citizen-law/law";
import { useCitizenLang } from "./useCitizenLang";

/**
 * The verified answer stays in English below this. A translation appears above it when
 * one passes its check, and nothing appears when none does, apart from a short note.
 */
export default function TranslatedAnswer({ messageId, render }: { messageId: string; render: (text: string) => React.ReactNode }) {
  const { lang, t } = useCitizenLang(true);
  const [state, setState] = useState<{ lang: Lang; text: string | null; failed: boolean } | null>(null);
  useEffect(() => {
    if (lang === "en") return;
    const controller = new AbortController();
    setState(null);
    translateAnswer(messageId, lang, controller.signal)
      .then(text => setState({ lang, text, failed: false }))
      .catch(() => { if (!controller.signal.aborted) setState({ lang, text: null, failed: true }); });
    return () => controller.abort();
  }, [lang, messageId]);
  if (lang === "en") return null;
  if (!state) return <p className="ctz-translation-note" role="status"><Loader2 size={14} className="animate-spin" aria-hidden="true" /> {t("translating")}</p>;
  if (state.failed || !state.text) return <p className="ctz-translation-note" role="status"><Languages size={14} aria-hidden="true" /> {t("translationFailed")}</p>;
  return <section className="ctz-translation" lang={lang} aria-label={t("translationLabel")}>
    <p className="ctz-translation-note"><Languages size={14} aria-hidden="true" /> {t("translationNote")}</p>
    <div className="legal-answer">{render(state.text)}</div>
  </section>;
}
