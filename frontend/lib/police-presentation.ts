/**
 * What the police screens say, kept where it can be tested.
 *
 * The rule across all of it: a state nobody established reads as exactly that. Each
 * "cannot be determined" below is a word of its own with a colour of its own, and
 * nothing that groups or counts rows is allowed to fold it into met or missed.
 */

import type {
  ChainState,
  ComplianceRecordItem,
  DraftType,
  ElementState,
  OffenceFinding,
  RegisterFilters,
  RegisterRow,
  RegisterState,
  SearchFinding,
  SearchVerdict,
} from "@/lib/types-police";

type Tone = "bad" | "warn" | "ok" | "plain";
export interface Words { label: string; tone: Tone }

export const REGISTER_WORDS: Record<RegisterState, Words> = {
  breached: { label: "Breached", tone: "bad" },
  overdue: { label: "Overdue", tone: "bad" },
  due: { label: "Due", tone: "plain" },
  met: { label: "Met", tone: "ok" },
  unknown: { label: "Cannot be determined", tone: "warn" },
};

export function registerWords(row: Pick<RegisterRow, "state" | "is_imminent">): Words {
  if (row.state === "due" && row.is_imminent) return { label: "Due soon", tone: "warn" };
  return REGISTER_WORDS[row.state];
}

export interface RegisterSection {
  key: "act_now" | "breached" | "unknown" | "coming_up" | "others" | "met";
  title: string;
  hint: string;
  rows: RegisterRow[];
}

/**
 * Sections in the order an officer has to read them. What can still be acted on comes
 * first, then what the record shows was missed, then what cannot be told at all. A
 * duty somebody else owes gets its own section, so it never reads as the officer's
 * lapse, and a met row is last rather than absent.
 */
export function groupRegister(rows: RegisterRow[]): RegisterSection[] {
  const sections: RegisterSection[] = [
    { key: "act_now", title: "Act now", hint: "Past the limit with no completion recorded, or expiring soon.", rows: [] },
    { key: "breached", title: "Breached on record", hint: "Recorded as done after the limit passed.", rows: [] },
    { key: "unknown", title: "Cannot be determined", hint: "Not a finding either way. Each says what is missing.", rows: [] },
    { key: "coming_up", title: "Coming up", hint: "Not yet expired.", rows: [] },
    { key: "others", title: "Someone else's duty", hint: "A Magistrate's or a doctor's period. Watch it; it is not an officer's breach.", rows: [] },
    { key: "met", title: "Met", hint: "Recorded as done within the limit.", rows: [] },
  ];
  const at = (key: RegisterSection["key"]) => sections.find((s) => s.key === key)!.rows;
  for (const row of rows) {
    if (!row.is_officer_duty) at("others").push(row);
    else if (row.state === "overdue" || (row.state === "due" && row.is_imminent)) at("act_now").push(row);
    else if (row.state === "breached") at("breached").push(row);
    else if (row.state === "unknown") at("unknown").push(row);
    else if (row.state === "due") at("coming_up").push(row);
    else at("met").push(row);
  }
  return sections.filter((section) => section.rows.length > 0);
}

export function registerQuery(filters: Partial<RegisterFilters>): string {
  const params = new URLSearchParams();
  for (const state of filters.states ?? []) params.append("state", state);
  if (filters.caseId) params.set("case_id", filters.caseId);
  if (filters.provision?.trim()) params.set("provision", filters.provision.trim());
  if (filters.imminentOnly) params.set("imminent_only", "true");
  if (filters.officerOnly) params.set("officer_only", "true");
  if (filters.includeClosed) params.set("include_closed", "true");
  return params.toString();
}

/** "3 hr left", "2 days overdue". The whole number that cannot flatter the officer. */
export function timeLeft(dueAt: string, now: number): string {
  const ms = Date.parse(dueAt) - now;
  const hours = Math.abs(ms) / 3_600_000;
  const amount = hours < 48
    ? `${ms >= 0 ? Math.floor(hours) : Math.ceil(hours)} hr`
    : `${ms >= 0 ? Math.floor(hours / 24) : Math.ceil(hours / 24)} days`;
  return ms >= 0 ? `${amount} left` : `${amount} over`;
}

export function formatMoment(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Not recorded";
  return parsed.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function formatDay(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "Not recorded";
  return parsed.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function toLocalInput(value: string | null | undefined): string {
  if (!value) return "";
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}

export const ACTOR_WORDS: Record<string, string> = {
  investigating_officer: "Investigating officer",
  magistrate: "Magistrate's duty",
  medical_practitioner: "Medical practitioner's duty",
};

export const CHAIN_WORDS: Record<ChainState, Words> = {
  continuous: { label: "Continuous on record", tone: "ok" },
  broken: { label: "Break on record", tone: "bad" },
  cannot_be_determined: { label: "Cannot be determined", tone: "warn" },
};

export const VERDICT_WORDS: Record<SearchVerdict, Words> = {
  met: { label: "Met", tone: "ok" },
  not_met: { label: "Not met", tone: "bad" },
  cannot_be_determined: { label: "Cannot be determined", tone: "warn" },
  not_applicable: { label: "Does not apply", tone: "plain" },
};

/** Never "legal" or "illegal": a court says that, and this reads a record. */
export const FINDING_WORDS: Record<SearchFinding, Words & { detail: string }> = {
  defect_on_record: { label: "Defect on record", tone: "bad", detail: "At least one requirement is recorded as not met." },
  incomplete_record: { label: "Record incomplete", tone: "warn", detail: "No failure is recorded, but some requirements cannot be determined." },
  no_defect_on_record: { label: "No defect on record", tone: "ok", detail: "Every requirement that applies is recorded as met. This is not a ruling that the search was lawful." },
};

export const ELEMENT_WORDS: Record<ElementState, Words> = {
  established: { label: "Established", tone: "ok" },
  not_established: { label: "Not established", tone: "bad" },
  cannot_be_determined: { label: "Cannot be determined", tone: "warn" },
};

export const OFFENCE_FINDING_WORDS: Record<OffenceFinding, Words & { detail: string }> = {
  all_elements_supported: { label: "Every element has support", tone: "ok", detail: "On your own assessment, with something on record behind each element. This is not a finding that the offence is made out." },
  element_not_established: { label: "An element is not established", tone: "bad", detail: "You have marked at least one element as not established." },
  cannot_be_determined: { label: "Cannot be determined", tone: "warn", detail: "At least one element has not been assessed, or has nothing on record behind it." },
};

export const TRI_WORDS = { yes: "Yes", no: "No", unknown: "Not recorded" } as const;

/** F14: the row's status moves through three states, and is what gets sent. */
export const NEXT_COMPLIANCE: Record<ComplianceRecordItem["status"], ComplianceRecordItem["status"]> = {
  not_recorded: "satisfied",
  satisfied: "not_satisfied",
  not_satisfied: "not_recorded",
};

/** F22: "loading" and "failed" are different, and neither is "nothing recorded". */
export type CaseTimelineState<T> = { kind: "loading" } | { kind: "none" } | { kind: "failed" } | { kind: "loaded"; timeline: T };

export function caseTimelineMessage(
  state: CaseTimelineState<{ undetermined: string[]; deadlines: unknown[] }>,
): string {
  switch (state.kind) {
    case "loading":
      return "Reading the timeline…";
    case "failed":
      return "The timeline could not be read. Nothing is implied about the deadlines.";
    case "none":
      return "No dates recorded for this case yet, so no BNSS period can be computed. Record the arrest, remand and information dates to start the clock.";
    case "loaded":
      return `No deadline can be computed yet: ${state.timeline.undetermined.length} of ${state.timeline.deadlines.length} depend on dates that are not recorded.`;
  }
}

/** F20: once a chat has a session, the server holds its scope. The picker must say so. */
export function scopeLockedReason(sessionId: string | null | undefined): string | null {
  return sessionId ? "This chat's scope is fixed. Start a new chat to change it." : null;
}

export interface DraftField { key: string; label: string; long?: boolean }

/** Only what the record cannot supply. The rest comes from the case. */
export const DRAFT_FIELDS: Record<DraftType, DraftField[]> = {
  s35_3_notice: [
    { key: "person_name", label: "Person noticed" },
    { key: "person_address", label: "Address" },
    { key: "offence_sections", label: "Offence sections" },
    { key: "grounds", label: "Substance of the complaint or information", long: true },
    { key: "appear_at", label: "Place of appearance" },
    { key: "appear_on", label: "Date and time of appearance" },
    { key: "rank_and_station", label: "Rank and police station" },
    { key: "issue_date", label: "Date of issue" },
  ],
  s94_production_order: [
    { key: "person_name", label: "Person in possession or power" },
    { key: "person_address", label: "Address" },
    { key: "thing_to_produce", label: "Document, communication, device or thing", long: true },
    { key: "basis", label: "Why it is believed to be in their possession", long: true },
    { key: "produce_at", label: "Place of production" },
    { key: "produce_on", label: "Date and time of production" },
    { key: "station", label: "Police station" },
    { key: "issue_date", label: "Date of issue" },
  ],
  seizure_memo: [
    { key: "place", label: "Place searched, if no search record is chosen" },
    { key: "occupant", label: "Occupant or person attending" },
    { key: "recording_reference", label: "Audio-video recording reference" },
    { key: "copy_delivered", label: "Copy delivered to the occupant" },
    { key: "seizure_reported", label: "Seizure report to the Magistrate" },
  ],
  case_diary_entry: [
    { key: "entry_date", label: "Date, if not drafting from a diary page" },
    { key: "circumstances", label: "Circumstances ascertained", long: true },
    { key: "places_visited", label: "Places visited" },
    { key: "statements_inserted", label: "Statements inserted" },
  ],
  remand_application: [
    { key: "magistrate", label: "Magistrate" },
    { key: "accused_name", label: "Accused" },
    { key: "offence_sections", label: "Offence sections" },
    { key: "custody_sought", label: "Custody sought (police or judicial)" },
    { key: "days_sought", label: "Days sought" },
    { key: "grounds", label: "Grounds for believing the accusation well-founded", long: true },
    { key: "why_necessary", label: "Why further detention is necessary", long: true },
    { key: "rank", label: "Applicant's rank" },
    { key: "application_date", label: "Date of application" },
  ],
  chargesheet_skeleton: [
    { key: "magistrate", label: "Magistrate" },
    { key: "parties", label: "Names of the parties", long: true },
    { key: "nature_of_information", label: "Nature of the information", long: true },
    { key: "offence_finding", label: "Whether an offence appears committed, and by whom", long: true },
    { key: "released_on_bond", label: "Released on bond or bail bond" },
    { key: "forwarded_in_custody", label: "Forwarded in custody under s.190" },
    { key: "medical_report", label: "Medical examination report attached (clause (h))" },
    { key: "report_date", label: "Date of report" },
  ],
};

export const DRAFT_TITLES: Record<DraftType, string> = {
  s35_3_notice: "Notice of appearance, s.35(3)",
  s94_production_order: "Order to produce, s.94",
  seizure_memo: "Seizure memo",
  case_diary_entry: "Case diary entry, s.192",
  remand_application: "Remand application, s.187",
  chargesheet_skeleton: "Chargesheet skeleton, s.193(3)",
};

/** Text that must never leave the screen without its warning. */
export function draftForClipboard(draft: { rendered_text: string; disclaimer: string }): string {
  return draft.rendered_text.includes(draft.disclaimer)
    ? draft.rendered_text
    : `${draft.rendered_text}\n\n---\n${draft.disclaimer}`;
}

/** Trims empties, and a cleared value goes out as null so a mistake can be undone. */
export function cleanForm(values: Record<string, string>): Record<string, string | null> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value.trim() ? value.trim() : null]));
}

export function sumCounts(counts: Record<string, number>, keys: string[]): number {
  return keys.reduce((total, key) => total + (counts[key] ?? 0), 0);
}

/** Which rail entries this officer has. A supervisor grant is the only condition. */
export function supervisedUnits<T extends { my_role: string }>(units: T[]): T[] {
  return units.filter((unit) => unit.my_role === "supervisor");
}
