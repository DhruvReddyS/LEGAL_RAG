/** Shapes of the police working record, as the API returns them. */

export type RegisterState = "breached" | "overdue" | "due" | "met" | "unknown";
export type TriState = "yes" | "no" | "unknown";

export interface RegisterRow {
  case_id: string;
  case_title: string;
  key: string;
  obligation: string;
  provision: string;
  actor: string;
  is_officer_duty: boolean;
  consequence: string;
  computed_from: string;
  due_at: string | null;
  state: RegisterState;
  state_reason: string;
  is_earliest_possible: boolean;
  is_imminent: boolean;
  completed_at: string | null;
  completion_note: string;
  completion_is_derived: boolean;
  notes: string[];
}

export interface RegisterResponse {
  evaluated_at: string;
  imminent_hours: number;
  rows: RegisterRow[];
  counts: Record<string, number>;
  cases_without_facts: { case_id: string; title: string }[];
}

export interface RegisterFilters {
  states: RegisterState[];
  caseId: string;
  provision: string;
  imminentOnly: boolean;
  officerOnly: boolean;
  includeClosed: boolean;
}

export type ComplianceRecordStatus = "satisfied" | "not_satisfied" | "not_recorded";

export interface ComplianceRecordItem {
  key: string;
  requirement: string;
  provision: string;
  consequence: string;
  applies_because: string;
  status: ComplianceRecordStatus;
  occurred_at: string | null;
  evidence_note: string | null;
  evidence_item_id: string | null;
  evidence_label: string | null;
  needs_record: boolean;
}

export interface ComplianceRecordList {
  action: string;
  items: ComplianceRecordItem[];
  flags: Record<string, boolean>;
}

export type ChainState = "continuous" | "broken" | "cannot_be_determined";

export interface CustodyEvent {
  id: string;
  occurred_at: string;
  from_person: string;
  to_person: string;
  purpose: string | null;
  place: string | null;
  corrects_event_id: string | null;
  created_at: string;
}

export interface EvidenceItem {
  id: string;
  case_id: string;
  exhibit_label: string;
  description: string;
  category: string;
  seized_at: string | null;
  seized_from: string | null;
  seized_by: string | null;
  search_id: string | null;
  status: string;
  storage_location: string | null;
  digital_hash: string | null;
  certificate_s63: TriState;
  reported_to_magistrate_at: string | null;
  notes: string | null;
  custody_events: CustodyEvent[];
  chain: { state: ChainState; current_holder: string | null; issues: string[] } | null;
}

export interface WitnessDuty {
  key: string;
  duty: string;
  provision: string;
  state: "done" | "not_done" | "cannot_be_determined";
}

export interface Witness {
  id: string;
  case_id: string;
  name: string;
  category: string;
  contact: string | null;
  attends_only_at_residence: boolean;
  needs_woman_officer: boolean;
  statement_recorded_at: string | null;
  statement_mode: string | null;
  recorded_by_woman_officer: TriState;
  inserted_in_diary: TriState;
  magistrate_statement_at: string | null;
  bond_executed_at: string | null;
  status: string;
  notes: string | null;
  duties: WitnessDuty[];
}

export type SearchVerdict = "met" | "not_met" | "cannot_be_determined" | "not_applicable";
export type SearchFinding = "defect_on_record" | "incomplete_record" | "no_defect_on_record";

export interface SearchCheck {
  key: string;
  requirement: string;
  provision: string;
  verdict: SearchVerdict;
  detail: string;
}

export interface SearchRecordRow {
  id: string;
  case_id: string;
  place: string;
  basis: "warrant" | "section_185" | "unknown";
  searched_at: string | null;
  grounds_recorded_at: string | null;
  record_sent_to_magistrate_at: string | null;
  recording_forwarded_at: string | null;
  witness_count: number | null;
  answers: Record<string, TriState>;
  notes: string | null;
  finding: SearchFinding;
  counts: Record<string, number>;
  checks: SearchCheck[];
}

export interface SearchQuestions {
  conditions: { key: string; question: string }[];
  questions: { key: string; requirement: string; provision: string; applies_to: string; only_if: string }[];
}

export type ElementState = "established" | "not_established" | "cannot_be_determined";
export type OffenceFinding = "all_elements_supported" | "element_not_established" | "cannot_be_determined";

export interface OffenceElement {
  key: string;
  element: string;
  provision: string;
  source_quote: string;
  state: ElementState;
  evidence_item_ids: string[];
  witness_ids: string[];
  note: string;
}

export interface OffenceAssessment {
  offence_key: string;
  title: string;
  provision: string;
  limits: string;
  finding: OffenceFinding;
  elements: OffenceElement[];
}

export interface OffenceCatalogueEntry {
  key: string;
  title: string;
  provision: string;
  limits: string;
  element_count: number;
}

export interface RemandSummary {
  periods: {
    id: string;
    custody_type: "police" | "judicial";
    from_date: string;
    to_date: string;
    magistrate: string | null;
    order_reference: string | null;
  }[];
  police_days_used: number;
  police_days_left: number;
  judicial_days: number;
  first_remand_date: string | null;
  police_custody_window_ends: string | null;
  window_days: number | null;
  undetermined_because: string;
  findings: string[];
  provision: string;
}

export interface DiaryEntry {
  id: string;
  page_no: number;
  entry_date: string;
  information_reached_at: string | null;
  began_at: string | null;
  closed_at: string | null;
  places_visited: string | null;
  circumstances: string;
  statements_inserted: string | null;
  corrects_page: number | null;
  created_at: string;
}

export interface DiaryResponse {
  entries: DiaryEntry[];
  days_without_entry: string[];
}

export type DraftType =
  | "s35_3_notice"
  | "s94_production_order"
  | "seizure_memo"
  | "case_diary_entry"
  | "remand_application"
  | "chargesheet_skeleton";

export interface DraftSummary {
  id: string;
  draft_type: DraftType;
  title: string;
  version: number;
  status: string;
  missing_field_count: number;
  created_at: string;
}

export interface PoliceDraft {
  id: string;
  case_id: string;
  draft_type: DraftType;
  title: string;
  version: number;
  status: string;
  rendered_text: string;
  missing_fields: string[];
  provisions: string[];
  disclaimer: string;
  inputs: Record<string, unknown>;
  created_at: string;
}

export interface CaseFile {
  case_id: string;
  generated_at: string;
  included_witness_contact: boolean;
  html: string;
  missing_sections: string[];
}

export interface MyUnit {
  unit_id: string;
  unit_name: string;
  my_role: "member" | "supervisor";
  supervisors: string[];
}

export interface SupervisedDeadline {
  key: string;
  obligation: string;
  provision: string;
  actor: string;
  due_at: string | null;
  state: RegisterState;
  state_reason: string;
  is_imminent: boolean;
}

export interface SupervisedCase {
  case_id: string;
  title: string;
  officer_name: string;
  has_facts: boolean;
  counts: Record<string, number>;
  compliance: Record<string, number>;
  attention: SupervisedDeadline[];
}

export interface SupervisedUnit {
  unit_id: string;
  unit_name: string;
  evaluated_at: string;
  imminent_hours: number;
  officer_count: number;
  counts: Record<string, number>;
  compliance: Record<string, number>;
  cases: SupervisedCase[];
}

export interface PoliceUnit {
  id: string;
  name: string;
  members: { user_id: string; name: string; email: string; role: "member" | "supervisor" }[];
}
