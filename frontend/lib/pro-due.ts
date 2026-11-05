import { dayPhrase, eventStateMeta, formatDate } from "@/lib/advocate-presentation";
import { formatMoment, registerWords, timeLeft } from "@/lib/police-presentation";
import type { DueBucket, DueItem, DueTone } from "@/lib/pro-presentation";
import type { CalendarEvent } from "@/lib/types-advocate";
import type { RegisterRow } from "@/lib/types-police";

/**
 * A register row as one due item. The buckets follow groupRegister: a period someone
 * else owes never reads as the officer's own lapse.
 */
export function dueFromRegister(row: RegisterRow, now: number): DueItem {
  const words = registerWords(row);
  let bucket: DueBucket;
  if (!row.is_officer_duty) bucket = "others";
  else if (row.state === "overdue") bucket = "act_now";
  else if (row.state === "due" && row.is_imminent) bucket = "soon";
  else if (row.state === "breached") bucket = "breached";
  else if (row.state === "unknown") bucket = "unknown";
  else if (row.state === "due") bucket = "upcoming";
  else bucket = "done";
  return {
    id: `${row.case_id}:${row.key}`,
    caseId: row.case_id,
    caseTitle: row.case_title,
    title: row.obligation,
    when: row.due_at ? formatMoment(row.due_at) : "No date can be computed",
    relative: row.due_at && !row.completed_at ? timeLeft(row.due_at, now) : "",
    at: row.due_at ? Date.parse(row.due_at) : null,
    status: words.label,
    tone: (words.tone === "plain" ? "neutral" : words.tone) as DueTone,
    bucket,
    tag: row.provision,
  };
}

const KIND: Record<string, string> = { hearing: "Hearing", limitation: "Limitation", filing: "Filing", other: "Date" };

export function dueFromCalendar(event: CalendarEvent, caseTitle?: string): DueItem {
  const meta = eventStateMeta(event.state);
  const bucket: DueBucket = event.completed || event.state === "done"
    ? "done"
    : event.state === "overdue"
      ? "act_now"
      : event.state === "due_today" || event.state === "due_soon"
        ? "soon"
        : "upcoming";
  return {
    id: event.id,
    caseId: event.case_id,
    caseTitle: event.case_title ?? caseTitle ?? "",
    title: event.title,
    when: formatDate(event.due_on),
    relative: event.completed ? "" : dayPhrase(event.days_from_today),
    at: Date.parse(`${event.due_on}T00:00:00`),
    status: meta.label,
    tone: meta.tone as DueTone,
    bucket,
    tag: KIND[event.kind] ?? "Date",
  };
}
