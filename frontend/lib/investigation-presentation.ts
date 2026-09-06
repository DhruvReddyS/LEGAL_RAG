/**
 * How a statutory deadline should read on screen.
 *
 * Separated from the component so it can be tested, because the distinction
 * it draws is the one thing the whole feature exists to protect: a deadline
 * that could not be computed is neither met nor missed, and must not be
 * rendered as either.
 *
 * The API returns `is_breached: null` for those, never `false`. A UI that
 * treats null as falsy collapses the three states back into two and quietly
 * reports compliance nobody established.
 */

export type DeadlineState = "overdue" | "pending" | "undetermined";

export interface DeadlineLike {
  due_at: string | null;
  is_breached: boolean | null;
}

export function deadlineState(deadline: DeadlineLike): DeadlineState {
  // Checked first and on its own. Reading `is_breached` before due_at would
  // let a null fall through to the "not overdue" branch.
  if (deadline.due_at === null || deadline.is_breached === null) return "undetermined";
  return deadline.is_breached ? "overdue" : "pending";
}

/** Whether the row asserts the obligation was met. Only one state does. */
export function assertsCompliance(deadline: DeadlineLike): boolean {
  return deadlineState(deadline) === "pending";
}

export function summarise(deadlines: DeadlineLike[]): {
  tracked: number;
  overdue: number;
  undetermined: number;
} {
  let overdue = 0;
  let undetermined = 0;
  for (const deadline of deadlines) {
    const state = deadlineState(deadline);
    if (state === "overdue") overdue += 1;
    if (state === "undetermined") undetermined += 1;
  }
  return { tracked: deadlines.length, overdue, undetermined };
}
