"use client";

import { useEffect, useState } from "react";
import { useCitizenLang } from "@/components/citizen/useCitizenLang";
import { calendarAcrossCases } from "@/lib/api-advocate";
import { listDeadlines } from "@/lib/api-citizen";
import { getRegister } from "@/lib/api-police";
import { getLang, t as translate, type UiKey } from "@/lib/citizen-i18n";
import {
  dueAdvocateIds,
  dueCitizenIds,
  duePoliceIds,
  localDay,
  REMINDER_TAG,
  reminderPermission,
  remindOfNewItems,
  type PermissionState,
} from "@/lib/deadline-reminders";

const CHECK_EVERY_MS = 30 * 60 * 1000;
const PERMISSION_GRANTED_EVENT = "corpusil:reminders-granted";

function browserHost(): { Notification?: { permission: string } } | undefined {
  return typeof window === "undefined" ? undefined : (window as unknown as { Notification?: { permission: string } });
}

function storage(): Storage | null {
  try { return window.localStorage; } catch { return null; }
}

async function dueIdsFor(role: string, today: string): Promise<string[]> {
  if (role === "citizen") return dueCitizenIds((await listDeadlines()).items);
  if (role === "police") return duePoliceIds((await getRegister()).rows, today);
  if (role === "advocate") return dueAdvocateIds((await calendarAcrossCases()).events);
  return [];
}

/**
 * Renders nothing. While the app is open, and only once permission is granted,
 * looks for what is due. No request is made without that permission, or in a
 * page with no Notification support.
 */
export function DeadlineReminders({ role }: { role: string }) {
  useEffect(() => {
    let live = true;
    const check = async () => {
      if (reminderPermission(browserHost()) !== "granted") return;
      const today = localDay(new Date());
      let dueIds: string[];
      try { dueIds = await dueIdsFor(role, today); }
      catch { return; } // A failed check says nothing about the deadlines. The next one tries again.
      if (!live) return;
      remindOfNewItems({
        dueIds,
        today,
        store: storage(),
        notify: (count) => {
          const lang = role === "citizen" ? getLang() : "en";
          const body = count === 1 ? translate("reminderOne", lang) : translate("reminderMany", lang).replace("{n}", String(count));
          new Notification("Corpusil", { body, tag: REMINDER_TAG });
        },
      });
    };
    void check();
    const timer = window.setInterval(() => void check(), CHECK_EVERY_MS);
    window.addEventListener(PERMISSION_GRANTED_EVENT, check);
    return () => {
      live = false;
      window.clearInterval(timer);
      window.removeEventListener(PERMISSION_GRANTED_EVENT, check);
    };
  }, [role]);
  return null;
}

const STATE_TEXT: Record<Exclude<PermissionState, "default">, UiKey> = {
  granted: "remindersOn",
  denied: "remindersBlocked",
  unsupported: "remindersUnsupported",
};

/** The one place permission is asked for, and only when this button is pressed. */
export function ReminderSettings({ citizen }: { citizen: boolean }) {
  const { t } = useCitizenLang(citizen);
  const [state, setState] = useState<PermissionState>("unsupported");
  useEffect(() => { setState(reminderPermission(browserHost())); }, []);
  const ask = async () => {
    try {
      await Notification.requestPermission();
    } catch {
      // An old browser with no promise form, or one that refuses outright.
    }
    const next = reminderPermission(browserHost());
    setState(next);
    if (next === "granted") window.dispatchEvent(new Event(PERMISSION_GRANTED_EVENT));
  };
  return (
    <section className="settings-section">
      <h3>{t("remindersTitle")}</h3>
      <div className="setting-block">
        <div className="setting-copy">
          <strong>{t("remindersLabel")}</strong>
          <small>{state === "default" ? t("remindersHint") : t(STATE_TEXT[state])}</small>
        </div>
        {state === "default" && <button type="button" className="button-secondary" onClick={() => void ask()}>{t("remindersEnable")}</button>}
      </div>
    </section>
  );
}
