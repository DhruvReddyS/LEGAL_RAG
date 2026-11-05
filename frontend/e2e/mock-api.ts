import type { Page, Route } from "@playwright/test";

/**
 * The backend, as route interception, so these tests need no services. Anything a
 * test has not described answers 404, which is what a screen must already survive.
 */
export const API = "http://localhost:8000";
export type Role = "citizen" | "police" | "advocate" | "admin";

const NOW = "2026-11-05T09:00:00Z";
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

export const SESSION_ID = uuid(1);
export const MESSAGE_ID = uuid(2);
export const JOB_ID = uuid(3);
export const CASE_ID = uuid(4);
export const SECOND_CASE_ID = uuid(5);

export function userFor(role: Role) {
  return { id: uuid(10), name: `Test ${role}`, email: `${role}@example.test`, role, is_active: true, created_at: NOW };
}

export const CITATION = {
  number: 1,
  chunk_id: "chunk-1",
  source_id: "bnss-2023",
  title: "The Bharatiya Nagarik Suraksha Sanhita, 2023",
  page_start: 52,
  page_end: 53,
  section: "173",
  excerpt: "Every information relating to the commission of a cognizable offence may be given orally or by electronic communication.",
  source_type: "statute",
  verification_status: "verified",
  current_status: "current",
};

export const ANSWER = {
  session_id: SESSION_ID,
  message_id: MESSAGE_ID,
  answer: "Information about a cognizable offence may be given to an officer in charge of a police station [Source 1].",
  citations: [CITATION],
  confidence_score: 0.9,
  evidence_strength: "strong",
  section_confidence: [],
  intent: {},
  agent_trace: [],
  response_mode: "fast",
  requested_mode: "auto",
  routing_reason: "fast_lane",
  routing_signals: [],
  timings_ms: { api_total_ms: 420 },
  pipeline_metrics: [],
  latency_target_ms: 5000,
  target_met: true,
  delivery_state: "complete",
  job_id: null,
  escalation_threshold: null,
};

export const ESCALATED = {
  ...ANSWER,
  message_id: null,
  answer: "",
  citations: [],
  response_mode: "deep",
  delivery_state: "searching_more_thoroughly",
  job_id: JOB_ID,
};

const PRIVACY = {
  notice: {
    version: "2026-03-04",
    personal_data: [{ item: "Account details", detail: "Your name, email address and role." }],
    purposes: ["To answer your questions."],
    what_does_not_happen: ["Your questions do not train a model."],
    known_exceptions: ["Voice uses your browser's service."],
  },
  data_fiduciary: "Test operator",
  grievance: { configured: false, name: null, email: null, phone: null, address: null },
  retention: { chat_retention_days: 365, chats_kept_until_deleted: false },
  self_service_reset: true,
};

function accountStatus(consentRequired: boolean) {
  return {
    mfa_enabled: false,
    mfa_pending: false,
    recovery_codes_remaining: 0,
    must_change_password: false,
    password_changed_at: NOW,
    consent: {
      current_version: "2026-03-04",
      accepted_version: consentRequired ? null : "2026-03-04",
      accepted_at: consentRequired ? null : NOW,
      withdrawn_at: null,
      required: consentRequired,
    },
  };
}

const LEGAL_CASE = { id: CASE_ID, title: "State v. Test", status: "open", role_type: "advocate", created_at: NOW, updated_at: NOW };
const SECOND_CASE = { id: SECOND_CASE_ID, title: "State v. Second", status: "open", role_type: "advocate", created_at: "2026-10-20T09:00:00Z", updated_at: NOW };

const registerRow = (caseId: string, caseTitle: string, key: string, obligation: string, provision: string, state: string, dueAt: string | null, imminent = false) => ({
  case_id: caseId, case_title: caseTitle, key, obligation, provision, actor: "officer", is_officer_duty: true, consequence: "", computed_from: "",
  due_at: dueAt, state, state_reason: "From the dates recorded.", is_earliest_possible: false, is_imminent: imminent, completed_at: null,
  completion_note: "", completion_is_derived: false, notes: [],
});

const REGISTER = {
  evaluated_at: NOW,
  imminent_hours: 48,
  rows: [
    registerRow(CASE_ID, LEGAL_CASE.title, "production", "Produce the arrested person before the Magistrate", "s.58 BNSS", "overdue", "2026-11-04T09:00:00Z"),
    registerRow(CASE_ID, LEGAL_CASE.title, "report", "File the final report", "s.193 BNSS", "due", "2026-11-06T09:00:00Z", true),
    registerRow(SECOND_CASE_ID, SECOND_CASE.title, "diary", "Send the case diary", "s.192 BNSS", "due", "2026-12-20T09:00:00Z"),
  ],
  counts: { overdue: 1, due: 2, imminent: 1 },
  cases_without_facts: [],
};

const calendarEvent = (id: number, caseId: string, caseTitle: string, kind: string, title: string, dueOn: string, state: string, days: number) => ({
  id: uuid(id), case_id: caseId, case_title: caseTitle, kind, title, due_on: dueOn, notes: null, basis: {}, completed: state === "done", state, days_from_today: days,
});

const CALENDAR = {
  today: "2026-11-05",
  events: [
    calendarEvent(80, CASE_ID, LEGAL_CASE.title, "limitation", "File the appeal", "2026-11-02", "overdue", -3),
    calendarEvent(81, CASE_ID, LEGAL_CASE.title, "hearing", "Arguments on bail", "2026-11-07", "due_soon", 2),
    calendarEvent(82, SECOND_CASE_ID, SECOND_CASE.title, "hearing", "Framing of charges", "2026-12-01", "upcoming", 26),
    calendarEvent(83, SECOND_CASE_ID, SECOND_CASE.title, "limitation", "Revision petition", "2027-01-15", "upcoming", 71),
  ],
};

/** Each case answers with its own file, so a test can see one case's content leave. */
const caseFile = (caseId: string) => ({
  document_id: uuid(caseId === CASE_ID ? 90 : 91),
  storage_object_id: null,
  filename: caseId === CASE_ID ? "first-case-statement.pdf" : "second-case-order.pdf",
  doc_type: "other",
  uploaded_at: NOW,
  sha256: null,
  page_count: 4,
  chunk_count: 12,
});

/** What an empty, working case answers, keyed by the part after /cases/{id}/. */
function caseFixture(caseId: string, rest: string): unknown {
  const table: Record<string, unknown> = {
    "documents/indexed": { documents: [caseFile(caseId)] },
    "documents/generated": { documents: [] },
    chronology: { events: [{ date: "2026-10-01", precision: "day", text: `An event in ${caseId === CASE_ID ? "the first case" : "the second case"}.`, document_id: uuid(90), title: caseFile(caseId).filename, page_start: 1, page_end: 1 }], total_events: 1, documents_read: 1 },
    "investigation/facts": {},
    "investigation/timeline": { evaluated_at: NOW, deadlines: [], breached: [], undetermined: [] },
    "police/evidence": { items: [] },
    "police/witnesses": { witnesses: [] },
    "police/searches": { searches: [] },
    "police/offences": { assessments: [] },
    "police/remand": { periods: [], police_days_used: 0, police_days_left: 0 },
    "police/diary": { entries: [], days_without_entry: [] },
    "police/drafts": { drafts: [] },
    "advocate/calendar": { today: "2026-11-05", events: CALENDAR.events.filter((event) => event.case_id === caseId) },
    "advocate/work": { work: [] },
    "advocate/debates": { debates: [] },
    "strategy/defence-analyses": { analyses: [] },
  };
  return table[rest];
}

const counts = { passed: 3, failed: 1, skipped: 0, incomplete: 0, not_run: 1 };
const GATE = { key: "retrieval", name: "Retrieval gate", checks: "Recall at five", status: "failed", excerpt: "Recall below the bar." };
const ADMIN: Record<string, unknown> = {
  "/admin/console/health": {
    ready: true,
    report: {
      status: "ready",
      dependencies: { postgres: { status: "ready", duration_ms: 2 }, qdrant: { status: "unavailable", duration_ms: 40, error_type: "timeout" } },
      inference: { generation: "ollama" },
    },
    environment: "test",
    serving_collection: "legal_kb_v5",
    schema_revision: "abc123",
    job_worker_enabled: false,
    quarantined_documents: 1,
    jobs: {
      by_status: { queued: 1, failed: 1 },
      oldest_queued_at: NOW,
      recent: [{ id: JOB_ID, type: "deep_review", status: "failed", progress: 40, attempts: 2, error_code: "timeout", created_at: NOW }],
    },
  },
  "/admin/overview": {
    users_total: 5,
    police_active: 1,
    advocates_active: 1,
    staged_intakes: 0,
    validated_intakes: 0,
    published_intakes: 2,
    audit_events: 40,
  },
  "/admin/corpus/intakes": { intakes: [], total: 0 },
  "/admin/console/corpus/amendments": { has_run: false, findings: [], open_findings: 0, watch: [], watch_total: 0, page: 1, page_size: 25 },
  "/admin/console/quality/review": {
    measure: { claim_accuracy: null, interval_95: null, sample_size: 0, correct: 0, incorrect: 0, unsure: 0, unreviewed: 0, answers_reviewed: 0 },
    total: 0,
    page: 1,
    page_size: 10,
    items: [],
  },
  "/admin/console/release": {
    serving_collection: "legal_kb_v5",
    collections: { reachable: true, collections: [{ name: "legal_kb_v5", points: 120000, status: "green" }, { name: "legal_kb_v6", points: 130000, status: "green" }] },
    evidence: [{ label: "v5", gates: [GATE], counts, all_passed: false, has_summary: true, updated_at: NOW, documents: ["SUMMARY.md"] }],
    decisions: [{
      id: uuid(20),
      label: "v5",
      collection: "legal_kb_v5",
      decision: "refuse",
      reason: "Retrieval below the bar",
      override_failed_gates: false,
      gate_snapshot: { counts, gates: { retrieval: "failed" } },
      decided_by: "Test admin",
      decided_at: NOW,
    }],
    gate_runs: [{ id: uuid(21), label: "v5", collection: "legal_kb_v5", status: "queued", exit_code: null, requested_at: NOW, started_at: null, finished_at: null }],
    queue_blockers: ["The gate runner is not running."],
    runner_command: "python scripts/run_queued_gates.py",
    rollback: { collection: "legal_kb_v4", steps: [{ title: "Point the API back", command: "export COLLECTION=legal_kb_v4", detail: "Restart afterwards." }] },
    live_switch_supported: false,
  },
  "/admin/console/corpus": {
    total_documents: 1570,
    total_pages: 90000,
    total: 1,
    page: 1,
    page_size: 25,
    quarantined: 1,
    facets: { source_type: { statute: 1 }, domain: { criminal: 1 }, currency: { current: 1 }, queue: { ocr: 1, verification: 0, currency: 0 } },
    documents: [{
      canonical_document_id: "bnss-2023",
      title: "Bharatiya Nagarik Suraksha Sanhita, 2023",
      source_type: "statute",
      category: "central_act",
      domain: "criminal",
      jurisdiction: "India",
      act_name: "BNSS",
      court: null,
      current_status: "current",
      currency_flag: "current",
      currency_note: null,
      superseded_by: null,
      verified_official: true,
      quality_status: "ok",
      ocr_required: true,
      page_count: 200,
      source_url: null,
      queues: ["ocr"],
      quarantined: false,
      work_status: "open",
      work_note: null,
    }],
  },
  "/admin/console/quality": {
    stored: {
      answers: [{ id: uuid(30), at: NOW, collection: "legal_kb_v5", abstention_correct: 0.9, ground_coverage: 0.8, citation_coverage: 0.95, currency_correct: 1, unsupported_claims_total: 2, latency_p50_s: 12 }],
      retrieval: [{ id: uuid(31), at: NOW, collection: "legal_kb_v5", recall_at_5: 0.9, citation_accuracy_at_5: 0.8, abstention_accuracy: 0.9, false_abstention_rate: 0.1 }],
    },
    live: {
      days: 30,
      series: [
        { day: "2026-11-04", answers: 10, abstention_rate: 0.1, citation_coverage: 0.9, unsupported_claims: 0, verified_answers: 8, latency_p50_ms: 900, latency_p95_ms: 4000, feedback_down: 1, feedback_total: 3 },
        { day: "2026-11-05", answers: 8, abstention_rate: 0.2, citation_coverage: 0.8, unsupported_claims: 1, verified_answers: 6, latency_p50_ms: 800, latency_p95_ms: 3000, feedback_down: 0, feedback_total: 1 },
      ],
      totals: { answers: 18, abstention_rate: 0.15, citation_coverage: 0.85, unsupported_claims: 1, verified_answers: 14, latency_p50_ms: 850, latency_p95_ms: 3500, feedback_down: 1, feedback_total: 4 },
    },
  },
  "/admin/console/feedback": {
    total: 1,
    page: 1,
    page_size: 25,
    items: [{ id: uuid(40), message_id: MESSAGE_ID, rating: "down", has_correction: true, status: "open", confidence_score: 0.4, citation_count: 1, answered_at: NOW, case_linked: false, role: "citizen" }],
  },
  "/admin/console/quarantine": {
    quarantines: [{ id: uuid(41), canonical_document_id: "old-act", title: "Old Act", reason: "Bad OCR", feedback_id: null, quarantined_at: NOW, released_at: null, release_reason: null }],
  },
  "/admin/console/users": {
    total: 1,
    page: 1,
    page_size: 25,
    by_role: { citizen: 1 },
    users: [{ id: uuid(50), name: "A Citizen", email: "a@example.test", role: "citizen", is_active: true, created_at: NOW, case_count: 0, last_login_at: NOW, sessions_valid_from: null, force_password_reset: false, mfa_required: false, suspended_reason: null, manageable: true }],
  },
  "/police/units": { units: [] },
  "/admin/console/retention": {
    categories: [{ key: "chat", label: "Conversations", description: "Chats and their answers.", minimum_days: 30, days: null }],
    runs: [],
    dry_run_valid_minutes: 15,
  },
  "/admin/console/models": {
    generation: { model: "qwen3", concurrency: 1, keep_alive: "5m", small_tier: false },
    serving_collection: "legal_kb_v5",
    prompts: [{ name: "answer", fingerprint: "abc", measured_in_latest_run: true }],
    latest_run: uuid(60),
    change_steps: [{ title: "Edit the setting", command: "GENERATION_MODEL=...", detail: "Then restart." }],
  },
  "/admin/console/evaluations": {
    runs: [{ id: uuid(60), kind: "answers", generated_at: NOW, collection: "legal_kb_v5", golden_set: "v3", generation_model: "qwen3", embedding_model: "bge", prompt_versions: { answer: "abc" }, metrics: { recall: 0.9 }, by_role: {} }],
  },
  "/admin/console/audit": {
    total: 1,
    page: 1,
    page_size: 25,
    actions: ["login"],
    resource_types: ["user"],
    events: [{ id: uuid(70), actor_name: "Test admin", actor_email: "admin@example.test", action: "login", resource_type: "user", resource_id: uuid(50), metadata: { note: "ok" }, timestamp: NOW }],
  },
};

export interface MockOptions {
  /** Null is a visitor who has not signed in. */
  role: Role | null;
  consentRequired?: boolean;
  /** Who a successful sign-in becomes. */
  signsInAs?: Role;
  /** A professional who has not opened a case yet. */
  noCases?: boolean;
  /** Keyed "METHOD /path". Wins over everything below. */
  overrides?: Record<string, (route: Route) => unknown>;
}

const cors = (route: Route) => ({
  "Access-Control-Allow-Origin": route.request().headers().origin ?? "*",
  "Access-Control-Allow-Credentials": "true",
});

export const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", headers: cors(route), body: JSON.stringify(body) });

export async function mockApi(page: Page, options: MockOptions) {
  let role = options.role;
  let consentRequired = options.consentRequired ?? false;
  await page.route(`${API}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { ...cors(route), "Access-Control-Allow-Headers": "*, content-type", "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE" } });
    }
    const override = options.overrides?.[`${request.method()} ${path}`];
    if (override) return override(route);

    if (path === "/auth/cookie/login") {
      role = options.signsInAs ?? "citizen";
      return json(route, userFor(role));
    }
    if (path === "/auth/me" || path === "/auth/cookie/refresh") {
      return role ? json(route, userFor(role)) : json(route, { detail: "Not authenticated" }, 401);
    }
    if (path === "/auth/cookie/logout") {
      role = null;
      return json(route, { ok: true });
    }
    if (!role) return json(route, { detail: "Not authenticated" }, 401);

    if (path === "/account/status") return json(route, accountStatus(consentRequired));
    if (path === "/account/privacy") return json(route, PRIVACY);
    if (path === "/account/consent") {
      consentRequired = false;
      return json(route, accountStatus(false).consent);
    }
    if (path === "/account/law-changes") return json(route, { unread: 0, notices: [] });
    if (path === "/history/sessions") return json(route, { items: [], next_cursor: null });
    if (path === "/history/matters") return json(route, { items: [] });
    if (path === "/citizen/matter/deadlines") return json(route, { items: [], today: "2026-11-05" });
    if (path === "/chat/safety-check") return json(route, { contacts: [] });
    if (path === "/chat/query") return json(route, ANSWER);
    if (path === "/feedback") return json(route, { ok: true });
    if (path === "/cases") {
      const cases = role === "citizen" || role === "admin" || options.noCases ? [] : [{ ...LEGAL_CASE, role_type: role }, { ...SECOND_CASE, role_type: role }];
      return json(route, { cases, total: cases.length });
    }
    if (path === "/police/my-units") return json(route, { units: [] });
    if (path === "/police/deadlines" && role === "police") return json(route, options.noCases ? { ...REGISTER, rows: [], counts: {} } : REGISTER);
    if (path === "/advocate/calendar" && role === "advocate") return json(route, options.noCases ? { ...CALENDAR, events: [] } : CALENDAR);
    const inCase = path.match(/^\/cases\/([0-9a-f-]{36})\/(.+)$/);
    if (inCase && (role === "police" || role === "advocate")) {
      const body = caseFixture(inCase[1], inCase[2]);
      if (body !== undefined) return json(route, body);
    }
    const fixture = ADMIN[path];
    if (fixture && role === "admin") return json(route, fixture);
    return json(route, { detail: "Not found" }, 404);
  });
}

/** Opens the app signed in, past the redirect to the landing page. */
export async function openApp(page: Page, role: Role, extra: Partial<MockOptions> = {}) {
  await mockApi(page, { role, ...extra });
  await page.goto("/");
  await page.getByLabel("Legal research question").waitFor();
}

/** Opens the police or advocate application at a screen, and waits for its navigation. */
export async function openPro(page: Page, role: "police" | "advocate", path = "/", extra: Partial<MockOptions> = {}) {
  await mockApi(page, { role, ...extra });
  await page.goto(path);
  await page.locator(".pro-app").waitFor();
}
