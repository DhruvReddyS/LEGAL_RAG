/**
 * What the advocate tools say about a result. Pure, so it can be tested without a browser.
 *
 * Two rules live here because a slip in either misleads a lawyer. An unknown is never
 * rendered as a pass: `null` from the server stays "not recorded". And a judgment-based
 * result is never shown without its coverage statement.
 */

export type Tone = "ok" | "warn" | "bad" | "neutral";

const ROUTE_STATUS: Record<string, { label: string; tone: Tone }> = {
  entitled_on_text: { label: "Section reads “shall”", tone: "ok" },
  discretionary: { label: "Court’s discretion", tone: "neutral" },
  barred_on_text: { label: "Barred on the text", tone: "bad" },
  not_yet: { label: "Date not reached", tone: "neutral" },
  needs_review: { label: "Read the authorities", tone: "warn" },
  undetermined: { label: "Not determined", tone: "warn" },
  not_applicable: { label: "Does not fit", tone: "neutral" },
};

export function routeStatusMeta(status: string): { label: string; tone: Tone } {
  return ROUTE_STATUS[status] ?? { label: "Not determined", tone: "warn" };
}

const EVENT_STATE: Record<string, { label: string; tone: Tone; rank: number }> = {
  overdue: { label: "Overdue", tone: "bad", rank: 0 },
  due_today: { label: "Due today", tone: "bad", rank: 1 },
  due_soon: { label: "Due soon", tone: "warn", rank: 2 },
  upcoming: { label: "Upcoming", tone: "neutral", rank: 3 },
  done: { label: "Done", tone: "ok", rank: 4 },
};

export function eventStateMeta(state: string): { label: string; tone: Tone } {
  const found = EVENT_STATE[state];
  return found ? { label: found.label, tone: found.tone } : { label: "Upcoming", tone: "neutral" };
}

/** Most urgent first. An overdue limitation date must not sit below next month's hearing. */
export function sortEvents<T extends { state: string; due_on: string }>(events: readonly T[]): T[] {
  return [...events].sort((a, b) => {
    const rank = (EVENT_STATE[a.state]?.rank ?? 9) - (EVENT_STATE[b.state]?.rank ?? 9);
    return rank !== 0 ? rank : a.due_on.localeCompare(b.due_on);
  });
}

export function dayPhrase(days: number): string {
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  return days < 0 ? `${-days} days ago` : `in ${days} days`;
}

/** "2026-03-02" to "2 Mar 2026", without the timezone slipping it a day. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Not recorded";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return iso;
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${day} ${names[month - 1]} ${year}`;
}

const CURRENCY: Record<string, { label: string; tone: Tone }> = {
  current: { label: "In force", tone: "ok" },
  repealed: { label: "Repealed", tone: "bad" },
  superseded: { label: "Superseded", tone: "bad" },
  status_unverified: { label: "Currency not verified", tone: "warn" },
  not_applicable: { label: "Case file", tone: "neutral" },
};

/** The label on every citation. A label nobody recognises reads as unverified, never as in force. */
export function currencyMeta(source: { current_status?: string; repeal_label?: string; replaced_by?: string | null }): { label: string; tone: Tone } {
  if (source.repeal_label === "no_longer_in_force") {
    return { label: source.replaced_by ? `Repealed; see ${source.replaced_by}` : "Repealed", tone: "bad" };
  }
  if (source.repeal_label === "concerns_repealed_provision") {
    return { label: "Cites renumbered provisions", tone: "warn" };
  }
  return CURRENCY[source.current_status ?? ""] ?? CURRENCY.status_unverified;
}

const WORK_LABEL: Record<string, string> = {
  defence_analysis: "Defence analysis",
  bail_assessment: "Bail assessment",
  brief: "Brief",
  synopsis: "Synopsis",
  case_comparison: "Case comparison",
  opponent_check: "Opponent’s authorities",
  debate: "Debate",
};

export function workKindLabel(kind: string): string {
  if (kind.startsWith("draft:")) {
    const words = kind.slice(6).replaceAll("_", " ");
    return `Draft: ${words}`;
  }
  return WORK_LABEL[kind] ?? kind.replaceAll("_", " ");
}

/** Which view a saved item opens in. */
export function workView(kind: string): "draft" | "brief" | "bail" | "comparison" | "opponent" | "debate" | "defence" | "unknown" {
  if (kind.startsWith("draft:")) return "draft";
  if (kind === "brief" || kind === "synopsis") return "brief";
  if (kind === "bail_assessment") return "bail";
  if (kind === "case_comparison") return "comparison";
  if (kind === "opponent_check") return "opponent";
  if (kind === "debate") return "debate";
  if (kind === "defence_analysis") return "defence";
  return "unknown";
}

/** "" means nobody entered it, which is different from "no". */
export function triState(value: string): boolean | null {
  if (value === "yes") return true;
  if (value === "no") return false;
  return null;
}

export interface BailForm {
  routes: string[];
  classification: string;
  gravity: string;
  punishableWithDeathOrLife: string;
  maxPunishmentYears: string;
  informationRecordedOn: string;
  arrestedOn: string;
  firstRemandOn: string;
  reportFiled: string;
  reportFiledOn: string;
  inCustody: string;
  custodyStartedOn: string;
  earlierDetentionDays: string;
  delayByAccusedDays: string;
  firstTimeOffender: string;
  otherCasesPending: string;
  previousConvictionBar: string;
  childWomanSickOrInfirm: string;
  involvesBns65Or702: string;
  triableByMagistrate: string;
  firstEvidenceDate: string;
  inCustodyWholeTrial: string;
  offenceDescription: string;
}

export const EMPTY_BAIL_FORM: BailForm = {
  routes: [], classification: "unknown", gravity: "unknown", punishableWithDeathOrLife: "",
  maxPunishmentYears: "", informationRecordedOn: "", arrestedOn: "", firstRemandOn: "",
  reportFiled: "", reportFiledOn: "", inCustody: "", custodyStartedOn: "", earlierDetentionDays: "",
  delayByAccusedDays: "", firstTimeOffender: "", otherCasesPending: "", previousConvictionBar: "",
  childWomanSickOrInfirm: "", involvesBns65Or702: "", triableByMagistrate: "", firstEvidenceDate: "",
  inCustodyWholeTrial: "", offenceDescription: "",
};

const orNull = (value: string) => value.trim() || null;

function count(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

/** The request body. Blanks go as null, so the server reports them missing rather than assuming. */
export function bailRequest(form: BailForm, save: boolean): Record<string, unknown> {
  const years = Number.parseFloat(form.maxPunishmentYears);
  return {
    routes: form.routes,
    classification: form.classification,
    gravity: form.gravity,
    punishable_with_death_or_life: triState(form.punishableWithDeathOrLife),
    max_punishment_months: Number.isFinite(years) && years >= 0 ? Math.round(years * 12) : null,
    information_recorded_on: orNull(form.informationRecordedOn),
    arrested_on: orNull(form.arrestedOn),
    first_remand_on: orNull(form.firstRemandOn),
    report_filed: triState(form.reportFiled),
    report_filed_on: orNull(form.reportFiledOn),
    in_custody: triState(form.inCustody),
    custody_started_on: orNull(form.custodyStartedOn),
    custody_days_before_current_spell: count(form.earlierDetentionDays),
    delay_by_accused_days: count(form.delayByAccusedDays),
    first_time_offender: triState(form.firstTimeOffender),
    other_cases_pending: triState(form.otherCasesPending),
    previous_conviction_bar: triState(form.previousConvictionBar),
    child_woman_sick_or_infirm: triState(form.childWomanSickOrInfirm),
    involves_bns_65_or_70_2: triState(form.involvesBns65Or702),
    triable_by_magistrate: triState(form.triableByMagistrate),
    first_evidence_date: orNull(form.firstEvidenceDate),
    in_custody_whole_trial_period: triState(form.inCustodyWholeTrial),
    offence_description: orNull(form.offenceDescription),
    save,
  };
}

/** Whether the court's own count of judgments could be read. Unknown scope is said out loud. */
export function coverageLines(coverage: { statement?: string; absence_note?: string } | null | undefined): [string, string] {
  return [
    coverage?.statement || "The number of judgments held could not be read, so the scope of this result is unknown.",
    coverage?.absence_note || "A judgment not found here is not evidence that none exists.",
  ];
}

export function debateIsActive(status: string): boolean {
  return status === "queued" || status === "running";
}

export function debateStatusLine(row: { status: string; turns_done: number; turns_total: number; attempt_count: number }, stage: string | null): string {
  if (row.status === "queued") {
    return row.attempt_count > 0
      ? `Queued to carry on. ${row.turns_done} of ${row.turns_total} turns already finished are kept.`
      : "Queued. It starts when the worker is free.";
  }
  if (row.status === "running") return stage || `Running. ${row.turns_done} of ${row.turns_total} turns finished.`;
  if (row.status === "succeeded") return `Finished. ${row.turns_total} turns.`;
  if (row.status === "cancelled") return `Cancelled after ${row.turns_done} of ${row.turns_total} turns.`;
  return `Stopped after ${row.turns_done} of ${row.turns_total} turns. What finished is shown below.`;
}

/** A draft leaves with its disclaimer attached. Pasted without it, it reads as finished. */
export function draftExportText(content: { rendered_text: string; disclaimer: string }): string {
  return content.rendered_text.includes(content.disclaimer)
    ? content.rendered_text
    : `${content.disclaimer}\n\n${content.rendered_text}`;
}

export function exportFilename(title: string, version: number): string {
  const slug = title.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase() || "draft";
  return `${slug}-v${version}.txt`;
}

export function groupArticles<T extends { division: string }>(articles: readonly T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of articles) groups.set(item.division, [...(groups.get(item.division) ?? []), item]);
  return [...groups.entries()];
}

/** Sides of a debate, by round, so a turn is read against the one it answers. */
export function turnsByRound<T extends { round: number; side: string }>(turns: readonly T[]): { round: number; for: T | null; against: T | null }[] {
  const rounds = new Map<number, { round: number; for: T | null; against: T | null }>();
  for (const turn of turns) {
    const row = rounds.get(turn.round) ?? { round: turn.round, for: null, against: null };
    if (turn.side === "for") row.for = turn;
    if (turn.side === "against") row.against = turn;
    rounds.set(turn.round, row);
  }
  return [...rounds.values()].sort((a, b) => a.round - b.round);
}
