/** C-10: what the dates mean on screen, and a calendar file for real reminders. */
import type { CitizenDeadline } from "./types-citizen";

/** A browser tab cannot wake a person up, so what is due is surfaced in the app and handed to their calendar. */
export function needsAttention(items: CitizenDeadline[]): CitizenDeadline[] {
  return items.filter(item => item.status === "overdue" || item.status === "due_today" || item.status === "due_soon");
}

export function dueLabel(item: Pick<CitizenDeadline, "status" | "days_left">, text: { done: string; today: string; overdue: (days: number) => string; left: (days: number) => string }): string {
  if (item.status === "done") return text.done;
  if (item.status === "due_today") return text.today;
  if (item.days_left < 0) return text.overdue(Math.abs(item.days_left));
  return text.left(item.days_left);
}

function escapeIcs(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

/** RFC 5545 asks lines to fold at 75 octets. */
function fold(line: string): string {
  const parts: string[] = [];
  let rest = line;
  while (rest.length > 70) {
    parts.push(rest.slice(0, 70));
    rest = rest.slice(70);
  }
  parts.push(rest);
  return parts.join("\r\n ");
}

function dateStamp(iso: string): string {
  return iso.replace(/-/g, "");
}

function nextDay(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

export function buildIcs(item: Pick<CitizenDeadline, "id" | "title" | "due_on" | "remind_days_before" | "notes" | "provision_label">, now = new Date()): string {
  const description = [item.notes, item.provision_label ? `Basis: ${item.provision_label}` : "", "Recorded by you in Corpusil. Check the date against the original paper."].filter(Boolean).join("\n");
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Corpusil//My matter//EN",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:${item.id}@corpusil`,
    `DTSTAMP:${now.toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`,
    `DTSTART;VALUE=DATE:${dateStamp(item.due_on)}`,
    `DTEND;VALUE=DATE:${dateStamp(nextDay(item.due_on))}`,
    `SUMMARY:${escapeIcs(item.title)}`,
    `DESCRIPTION:${escapeIcs(description)}`,
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    `DESCRIPTION:${escapeIcs(item.title)}`,
    `TRIGGER:-P${Math.max(item.remind_days_before, 0)}D`,
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return lines.map(fold).join("\r\n") + "\r\n";
}
