/**
 * What the police and advocate screens agree on: one shape for "something is due",
 * whichever register it came from, and how a list of cases is searched and sorted.
 * Nothing here decides a legal question. States and dates arrive from the server.
 */
export type DueTone = "bad" | "warn" | "neutral" | "ok";
export type DueBucket = "act_now" | "breached" | "soon" | "upcoming" | "unknown" | "others" | "done";

export interface DueItem {
  id: string;
  caseId: string;
  caseTitle: string;
  title: string;
  /** Exact wording for the date, or a statement that there is none. */
  when: string;
  /** "3 days left", "today". Empty when no date is known. */
  relative: string;
  /** Sort key. Null when no date can be computed. */
  at: number | null;
  status: string;
  tone: DueTone;
  bucket: DueBucket;
  /** The provision or the kind of date. */
  tag: string;
}

const RANK: Record<DueBucket, number> = { act_now: 0, breached: 1, soon: 2, upcoming: 3, unknown: 4, others: 5, done: 6 };

export function sortDue(items: readonly DueItem[]): DueItem[] {
  return [...items].sort((a, b) => {
    const rank = RANK[a.bucket] - RANK[b.bucket];
    if (rank) return rank;
    if (a.at === null) return b.at === null ? a.title.localeCompare(b.title) : 1;
    return b.at === null ? -1 : a.at - b.at;
  });
}

/** What goes on a dashboard: anything that can still be acted on or was missed, most urgent first. */
export function needsAttention(items: readonly DueItem[]): DueItem[] {
  return sortDue(items.filter((item) => item.bucket === "act_now" || item.bucket === "breached" || item.bucket === "soon"));
}

/** The next thing due per case. A finished item, a missed one or someone else's period is never next. */
export function nextDueByCase(items: readonly DueItem[]): Map<string, DueItem> {
  const next = new Map<string, DueItem>();
  for (const item of sortDue(items)) {
    if (item.bucket === "done" || item.bucket === "others" || item.bucket === "breached") continue;
    if (!next.has(item.caseId)) next.set(item.caseId, item);
  }
  return next;
}

export function countBuckets(items: readonly DueItem[]): Record<DueBucket, number> {
  const counts: Record<DueBucket, number> = { act_now: 0, breached: 0, soon: 0, upcoming: 0, unknown: 0, others: 0, done: 0 };
  for (const item of items) counts[item.bucket] += 1;
  return counts;
}

export type CaseStatusFilter = "open" | "closed" | "archived" | "all";
export type CaseSort = "urgent" | "activity" | "newest" | "title";

export interface CaseLike {
  id: string;
  title: string;
  status: string;
  created_at: string;
}

/** A case has no number of its own on record, so the start of its id stands in. */
export function caseReference(id: string): string {
  return id.replace(/-/g, "").slice(-8).toUpperCase();
}

export function visibleCases<T extends CaseLike>(
  cases: readonly T[],
  options: { query: string; status: CaseStatusFilter; sort: CaseSort; next: Map<string, DueItem>; activity: Map<string, number> },
): T[] {
  const needle = options.query.trim().toLowerCase();
  const kept = cases.filter((item) => {
    if (options.status !== "all" && item.status !== options.status) return false;
    return !needle || item.title.toLowerCase().includes(needle) || caseReference(item.id).toLowerCase().includes(needle);
  });
  const lastActivity = (item: T) => Math.max(options.activity.get(item.id) ?? 0, Date.parse(item.created_at) || 0);
  const byTitle = (a: T, b: T) => a.title.localeCompare(b.title);
  return kept.sort((a, b) => {
    if (options.sort === "title") return byTitle(a, b);
    if (options.sort === "newest") return (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0) || byTitle(a, b);
    if (options.sort === "activity") return lastActivity(b) - lastActivity(a) || byTitle(a, b);
    const [first, second] = [options.next.get(a.id), options.next.get(b.id)];
    if (first && second) return sortDue([first, second])[0] === first ? -1 : 1;
    if (first || second) return first ? -1 : 1;
    return lastActivity(b) - lastActivity(a) || byTitle(a, b);
  });
}

export function shortDate(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "" || value === 0) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
