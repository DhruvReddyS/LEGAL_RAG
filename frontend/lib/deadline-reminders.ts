/**
 * Which deadlines are due, and whether this browser has already said so today.
 * A notification shows on a locked phone, so its text carries a count and nothing
 * about any case. Ids are kept in storage only to avoid repeating a reminder.
 */

export const SEEN_STORAGE_KEY = "corpusil.reminders.seen";
export const REMINDER_TAG = "corpusil-deadlines";

export type PermissionState = "unsupported" | "default" | "granted" | "denied";

type NotificationHost = { Notification?: { permission: string } };

export function reminderPermission(host: NotificationHost | undefined): PermissionState {
  const state = host?.Notification?.permission;
  if (state === "granted" || state === "denied" || state === "default") return state;
  return "unsupported";
}

/** The day on the reader's own calendar, since "due today" is about their day. */
export function localDay(at: Date): string {
  const month = String(at.getMonth() + 1).padStart(2, "0");
  const day = String(at.getDate()).padStart(2, "0");
  return `${at.getFullYear()}-${month}-${day}`;
}

export function dueCitizenIds(items: { id: string; status: string; completed_at: string | null }[]): string[] {
  return items
    .filter(item => !item.completed_at && (item.status === "overdue" || item.status === "due_today"))
    .map(item => `citizen:${item.id}`);
}

export function dueAdvocateIds(events: { id: string; state: string; completed: boolean }[]): string[] {
  return events
    .filter(event => !event.completed && (event.state === "overdue" || event.state === "due_today"))
    .map(event => `advocate:${event.id}`);
}

export function duePoliceIds(
  rows: { case_id: string; key: string; state: string; due_at: string | null; completed_at: string | null }[],
  today: string,
): string[] {
  return rows
    .filter(row => {
      if (row.completed_at) return false;
      if (row.state === "breached" || row.state === "overdue") return true;
      return row.state === "due" && row.due_at !== null && localDay(new Date(row.due_at)) === today;
    })
    .map(row => `police:${row.case_id}:${row.key}`);
}

type Store = { getItem(key: string): string | null; setItem(key: string, value: string): void };

function readSeen(store: Store | null, today: string): Set<string> {
  try {
    const saved = JSON.parse(store?.getItem(SEEN_STORAGE_KEY) ?? "null") as { day?: unknown; ids?: unknown } | null;
    if (saved && saved.day === today && Array.isArray(saved.ids)) return new Set(saved.ids.map(String));
  } catch {
    // Storage disabled or unreadable: start the day over.
  }
  return new Set();
}

function writeSeen(store: Store | null, today: string, ids: Set<string>): void {
  try {
    store?.setItem(SEEN_STORAGE_KEY, JSON.stringify({ day: today, ids: Array.from(ids) }));
  } catch {
    // Storage disabled or full. A repeat reminder is the only cost.
  }
}

export interface ReminderCheck {
  dueIds: string[];
  today: string;
  store: Store | null;
  /** Makes the notification. May throw, as some phone browsers do. */
  notify: (count: number) => void;
}

/**
 * Says how many new items are due, once per item per day. Marked seen only after
 * the notification was made, so a failure can try again at the next check.
 */
export function remindOfNewItems({ dueIds, today, store, notify }: ReminderCheck): number {
  const seen = readSeen(store, today);
  const fresh = dueIds.filter(id => !seen.has(id));
  if (!fresh.length) return 0;
  try {
    notify(fresh.length);
  } catch {
    return 0;
  }
  fresh.forEach(id => seen.add(id));
  writeSeen(store, today, seen);
  return fresh.length;
}
