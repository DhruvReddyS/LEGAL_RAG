/**
 * The decisions the admin console makes about what to show.
 *
 * Kept free of React so the rules can be tested: which actions a release allows,
 * how a missing number reads, and how a chart breaks over a gap rather than
 * drawing a line through data that does not exist.
 */

export type Tone = "ok" | "warn" | "bad" | "neutral";

const GATE_TONES: Record<string, Tone> = {
  passed: "ok",
  failed: "bad",
  skipped: "warn",
  incomplete: "warn",
  not_run: "neutral",
};

const GATE_LABELS: Record<string, string> = {
  passed: "Passed",
  failed: "Failed",
  skipped: "Skipped",
  incomplete: "Incomplete",
  not_run: "Not run",
};

export function gateTone(status: string): Tone {
  return GATE_TONES[status] ?? "neutral";
}

export function gateLabel(status: string): string {
  return GATE_LABELS[status] ?? status;
}

const CURRENCY_LABELS: Record<string, string> = {
  current: "Current",
  unverified: "Status unverified",
  warned: "Currency warning",
  repealed_or_superseded: "Repealed or superseded",
};

export function currencyLabel(flag: string): string {
  return CURRENCY_LABELS[flag] ?? flag;
}

export function currencyTone(flag: string): Tone {
  if (flag === "current") return "ok";
  if (flag === "repealed_or_superseded") return "bad";
  return "warn";
}

/** "Police" is already plural: appending an s printed "Polices" on the Users tab. */
export function rolePluralLabel(role: string): string {
  return role === "police" ? "Police" : `${role[0].toUpperCase()}${role.slice(1)}s`;
}

/** "1 citation", "2 citations": the review and triage rows read one figure at a time. */
export function countOf(value: number, noun: string): string {
  return `${value.toLocaleString("en-IN")} ${noun}${value === 1 ? "" : "s"}`;
}

/** An empty value leaves the key out, so a filter that was cleared stops filtering. */
export function toQuery(filters: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

export interface PageSpan {
  first: number;
  last: number;
  pages: number;
  hasPrevious: boolean;
  hasNext: boolean;
}

export function pageSpan(page: number, pageSize: number, total: number): PageSpan {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return { first: 0, last: 0, pages, hasPrevious: page > 1, hasNext: false };
  const first = (page - 1) * pageSize + 1;
  return {
    first,
    last: Math.min(total, first + pageSize - 1),
    pages,
    hasPrevious: page > 1,
    hasNext: page < pages,
  };
}

/** Never a blank and never a zero for a number nobody measured. */
export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "Not measured" : `${(value * 100).toFixed(1)}%`;
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "Not measured" : value.toLocaleString("en-IN");
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "Not measured";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function formatDay(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
}

interface GateReading {
  all_passed: boolean;
  counts: Record<string, number>;
}

export interface DecisionRules {
  canApprove: boolean;
  needsOverride: boolean;
  summary: string;
}

/**
 * Approving over gates that have not all passed is possible, because a gate can
 * be wrong, but it takes an explicit override. The button must say so rather
 * than fail with a 409 after the reason has been typed.
 */
export function decisionRules(evidence: GateReading, override: boolean): DecisionRules {
  if (evidence.all_passed) {
    return { canApprove: true, needsOverride: false, summary: "All seven gates passed." };
  }
  const failed = evidence.counts.failed ?? 0;
  const unfinished =
    (evidence.counts.not_run ?? 0) + (evidence.counts.incomplete ?? 0) + (evidence.counts.skipped ?? 0);
  const parts: string[] = [];
  if (failed) parts.push(`${failed} failed`);
  if (unfinished) parts.push(`${unfinished} not finished`);
  return {
    canApprove: override,
    needsOverride: true,
    summary: `${parts.join(", ")}. This collection should not be promoted without a recorded reason.`,
  };
}

export const MIN_REASON_CHARACTERS = 10;

export function reasonIsSufficient(reason: string): boolean {
  return reason.trim().length >= MIN_REASON_CHARACTERS;
}

/** The latest decision for a collection, which is the one that stands. */
export function standingDecision<T extends { collection: string; decided_at: string }>(
  decisions: T[],
  collection: string,
): T | null {
  return decisions
    .filter(item => item.collection === collection)
    .reduce<T | null>(
      (latest, item) => (latest === null || item.decided_at > latest.decided_at ? item : latest),
      null,
    );
}

export function retentionError(
  value: string,
  minimum: number,
): string | null {
  const text = value.trim();
  if (text === "") return null;
  if (!/^\d+$/.test(text)) return "Enter a whole number of days, or leave it blank to keep everything.";
  if (Number(text) < minimum) return `Must be at least ${minimum} days.`;
  return null;
}

export const RETENTION_COUNT_LABELS: Record<string, string> = {
  chat_history: "Conversations",
  job_records: "Background jobs",
  audit_logs: "Audit rows",
  closed_cases: "Closed cases, from every store",
  closed_cases_failed: "Closed cases that could not be erased, kept for the next run",
  expired_refresh_tokens: "Expired session records",
};

export function totalToPurge(counts: Record<string, number>): number {
  return Object.entries(counts)
    .filter(([key]) => !key.endsWith("_failed"))
    .reduce((sum, [, value]) => sum + value, 0);
}

export function dryRunIsExpired(expiresAt: string, now: Date = new Date()): boolean {
  return new Date(expiresAt).getTime() <= now.getTime();
}

const METRIC_LABELS: Record<string, string> = {
  abstention_correct: "Abstention correct",
  abstention_accuracy: "Abstention accuracy",
  false_abstention_rate: "False abstention",
  ground_coverage: "Ground coverage",
  citation_coverage: "Citation coverage",
  citation_accuracy_at_5: "Citation accuracy at 5",
  currency_correct: "Currency correct",
  unsupported_claims_total: "Unsupported claims",
  latency_p50_s: "Latency p50, seconds",
  reading_grade_mean: "Reading grade",
  recall_at_1: "Recall at 1",
  recall_at_5: "Recall at 5",
  recall_at_20: "Recall at 20",
  mrr: "Mean reciprocal rank",
  ndcg_at_10: "nDCG at 10",
  seconds_per_query: "Seconds per query",
  items: "Items",
  ground_coverage_items: "Ground coverage items",
  currency_items: "Currency items",
};

export function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric.replace(/_/g, " ");
}

export function formatMetric(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not measured";
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}

export function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (value === 0) return "No change";
  return `${value > 0 ? "+" : ""}${Number.isInteger(value) ? value : value.toFixed(3)}`;
}

/** Audit metadata as label and value pairs. Nested values stay compact. */
export function metadataRows(metadata: Record<string, unknown>): [string, string][] {
  return Object.entries(metadata)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => [
      key.replace(/_/g, " "),
      typeof value === "object" ? JSON.stringify(value) : String(value),
    ]);
}

// ---------------------------------------------------------------- charts

export interface ChartPoint {
  label: string;
  value: number | null;
  detail?: string;
}

export interface PlacedPoint extends ChartPoint {
  x: number;
  y: number | null;
}

export interface ChartGeometry {
  points: PlacedPoint[];
  /** One SVG path per unbroken run. A gap in the data is a gap in the line. */
  segments: string[];
  /** A point with no neighbour draws no line, so it needs a marker. */
  ticks: { value: number; y: number }[];
  xLabels: { label: string; x: number }[];
  hasData: boolean;
}

export interface ChartBox {
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function niceCeiling(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}

export function chartGeometry(
  data: ChartPoint[],
  box: ChartBox,
  options: { max?: number; tickCount?: number; xLabelCount?: number; integer?: boolean } = {},
): ChartGeometry {
  const values = data.map(item => item.value).filter((value): value is number => value !== null);
  const wanted = options.tickCount ?? 3;
  // A count has whole-number ticks, or an axis reads 0, 1, 1, 2.
  const step = options.integer ? Math.max(1, Math.ceil(Math.max(0, ...values) / wanted)) : 0;
  const tickCount = options.integer ? Math.max(1, Math.ceil(Math.max(0, ...values) / step)) : wanted;
  const max = options.max ?? (options.integer ? step * tickCount : niceCeiling(Math.max(0, ...values)));
  const plotWidth = box.width - box.left - box.right;
  const plotHeight = box.height - box.top - box.bottom;
  const toY = (value: number) => box.top + plotHeight - (Math.min(value, max) / max) * plotHeight;
  const toX = (index: number) =>
    data.length <= 1 ? box.left + plotWidth / 2 : box.left + (index / (data.length - 1)) * plotWidth;

  const points: PlacedPoint[] = data.map((item, index) => ({
    ...item,
    x: toX(index),
    y: item.value === null ? null : toY(item.value),
  }));

  const segments: string[] = [];
  let run: PlacedPoint[] = [];
  const flush = () => {
    if (run.length > 1) {
      segments.push(
        run.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)} ${(point.y as number).toFixed(1)}`).join(" "),
      );
    }
    run = [];
  };
  for (const point of points) {
    if (point.y === null) flush();
    else run.push(point);
  }
  flush();

  const ticks = Array.from({ length: tickCount + 1 }, (_, index) => {
    const value = (max * index) / tickCount;
    return { value, y: toY(value) };
  });

  const labelCount = Math.min(options.xLabelCount ?? 5, data.length);
  const xLabels =
    labelCount <= 1
      ? points.slice(0, 1).map(point => ({ label: point.label, x: point.x }))
      : Array.from({ length: labelCount }, (_, index) => {
          const point = points[Math.round((index * (points.length - 1)) / (labelCount - 1))];
          return { label: point.label, x: point.x };
        }).filter((item, index, all) => index === 0 || item.label !== all[index - 1].label);

  return { points, segments, ticks, xLabels, hasData: values.length > 0 };
}

/** The point the pointer is over, for a crosshair that ignores gaps. */
export function nearestPoint(points: PlacedPoint[], x: number): PlacedPoint | null {
  let best: PlacedPoint | null = null;
  for (const point of points) {
    if (point.y === null) continue;
    if (best === null || Math.abs(point.x - x) < Math.abs(best.x - x)) best = point;
  }
  return best;
}
