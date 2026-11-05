"use client";
import { readTheme } from "@/lib/preferences";
import { useEffect, useState } from "react";
import RightsCard from "@/components/citizen/RightsCard";
import { LangSwitcher } from "@/components/citizen/shared";
import { useCitizenLang } from "@/components/citizen/useCitizenLang";
import { keepRightsPageOffline } from "@/lib/citizen-offline";

/**
 * C-04 in the place it is needed: no account, no network. A person being
 * arrested cannot sign in. The worker keeps this page and its assets on the
 * device after the first visit.
 */
export default function RightsPage() {
  const { t } = useCitizenLang();
  const [offlineReady, setOfflineReady] = useState(false);
  useEffect(() => {
    document.documentElement.dataset.theme = readTheme();
    const desktop = "__TAURI_INTERNALS__" in window || window.location.protocol === "tauri:";
    // The desktop app already holds this page on disk.
    if (desktop) { setOfflineReady(true); return; }
    if (!("serviceWorker" in navigator)) return;
    keepRightsPageOffline().then(setOfflineReady).catch(() => setOfflineReady(false));
  }, []);
  return <main className="ctz-public" data-role="citizen">
    <div className="ctz-public-top ctz-no-print">
      <a className="ctz-link" href="/">{t("signIn")}</a>
      <LangSwitcher/>
    </div>
    <h1>{t("rightsPublicTitle")}</h1>
    {offlineReady && <p className="ctz-offline ctz-no-print" role="status">{t("offlineReady")}</p>}
    <RightsCard/>
  </main>;
}
