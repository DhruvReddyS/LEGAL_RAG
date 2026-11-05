import { expect, test, type Page, type Route } from "@playwright/test";
import { json, MESSAGE_ID, openApp } from "./mock-api";

const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const openTab = async (page: Page, name: string) => {
  await page.locator(".feature-nav").getByRole("button", { name: "Manage workspace" }).click();
  await page.getByRole("tablist", { name: "Administration sections" }).getByRole("tab", { name }).click();
};

test("AD-06: a suspension needs a reason, and shows on the row afterwards", async ({ page }) => {
  const sent: unknown[] = [];
  let listed = 0;
  await openApp(page, "admin", {
    overrides: {
      "GET /admin/console/users": (route: Route) => {
        listed += 1;
        return json(route, { total: 1, page: 1, page_size: 25, by_role: { citizen: 1 }, users: [{ id: uuid(50), name: "A Citizen", email: "a@example.test", role: "citizen", is_active: sent.length === 0, created_at: "2026-11-05T09:00:00Z", case_count: 0, last_login_at: null, sessions_valid_from: null, force_password_reset: false, mfa_required: false, suspended_reason: sent.length ? "Abuse report" : null, manageable: true }] });
      },
      [`POST /admin/console/users/${uuid(50)}/suspend`]: (route: Route) => {
        sent.push(route.request().postDataJSON());
        return json(route, { id: uuid(50), name: "A Citizen", email: "a@example.test", role: "citizen", is_active: false, created_at: "2026-11-05T09:00:00Z", case_count: 0, last_login_at: null, sessions_valid_from: null, force_password_reset: false, mfa_required: false, suspended_reason: "Abuse report", manageable: true });
      },
    },
  });
  await openTab(page, "Users");
  await page.getByRole("button", { name: "Suspend" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Suspend" })).toBeDisabled();
  await dialog.locator("input, textarea").first().fill("Abuse report");
  await dialog.getByRole("button", { name: "Suspend" }).click();
  await expect(dialog).toHaveCount(0);
  expect(sent).toEqual([{ reason: "Abuse report", confirm: true }]);
  await expect(page.getByRole("button", { name: "Reactivate" })).toBeVisible();
  expect(listed).toBeGreaterThan(1);
});

test("AD-07: a purge runs only from a dry run, with the phrase typed", async ({ page }) => {
  const purged: unknown[] = [];
  await openApp(page, "admin", {
    overrides: {
      "POST /admin/console/retention/dry-run": (route: Route) => json(route, { id: uuid(80), counts: { chat: 3 }, cutoffs: { chat: "2026-01-01T00:00:00Z" }, policy: { chat: 30 }, created_at: "2026-11-05T09:00:00Z", expires_at: new Date(Date.now() + 15 * 60_000).toISOString(), confirmation: "PURGE 3" }),
      "POST /admin/console/retention/purge": (route: Route) => { purged.push(route.request().postDataJSON()); return json(route, { id: uuid(81), deleted: { chat: 3 } }); },
    },
  });
  await openTab(page, "Retention");
  await page.getByRole("button", { name: "Dry run" }).click();
  await page.getByRole("button", { name: /Purge/ }).first().click();
  const dialog = page.getByRole("dialog", { name: "Purge permanently" });
  const confirm = dialog.getByRole("button", { name: "Purge", exact: true });
  await expect(confirm).toBeDisabled();
  await dialog.locator("input").fill("PURGE 3");
  await confirm.click();
  await expect(dialog).toHaveCount(0);
  expect(purged).toEqual([{ dry_run_id: uuid(80), confirmation: "PURGE 3" }]);
});

test("AD-05: a bad answer traces to its sources and saves a triage", async ({ page }) => {
  const saved: unknown[] = [];
  await openApp(page, "admin", {
    overrides: {
      [`GET /admin/console/feedback/${uuid(40)}/trace`]: (route: Route) => json(route, { id: uuid(40), message_id: MESSAGE_ID, rating: "down", status: "open", note: null, confidence_score: 0.4, answered_at: "2026-11-05T09:00:00Z", case_linked: false, corpus_checked: true, answer: "A traced answer.", correction: "It is wrong.", has_correction: true, citations_withheld: 0, citations: [{ number: 1, chunk_id: "c1", title: "An Act", source_type: "statute", page_start: 1, page_end: 2, court: null, act_name: "An Act", section: "1", source_url: null, excerpt: "Some text.", retrieval_score: 0.5, verification_status: "verified", current_status: "current", replaced_by: null, canonical_document_id: "an-act", corpus_tier: "gold", found_in_corpus: true, quarantined: false }] }),
      [`PUT /admin/console/feedback/${uuid(40)}/triage`]: (route: Route) => { saved.push(route.request().postDataJSON()); return json(route, { status: "resolved" }); },
    },
  });
  await openTab(page, "Incidents");
  await page.getByRole("button", { name: /Trace/ }).click();
  const dialog = page.getByRole("dialog", { name: "Trace this answer" });
  await expect(dialog).toContainText("A traced answer.");
  await expect(dialog).toContainText("An Act");
  await dialog.locator("select").selectOption("resolved");
  await dialog.getByRole("button", { name: /Save/ }).click();
  await expect.poll(() => saved.length).toBe(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("AD-02: a refusal needs a reason and goes on the record", async ({ page }) => {
  const decisions: { decision: string; reason: string }[] = [];
  await openApp(page, "admin", {
    overrides: {
      "POST /admin/console/release/decisions": (route: Route) => {
        const body = route.request().postDataJSON();
        decisions.push(body);
        return json(route, { id: uuid(90), ...body, gate_snapshot: { counts: {}, gates: {} }, decided_by: "Test admin", decided_at: "2026-11-05T09:00:00Z" });
      },
    },
  });
  await openTab(page, "Release");
  const reason = page.locator("label", { hasText: "Reason" }).locator("textarea");
  await reason.fill("Retrieval is below the bar for this release.");
  await page.getByRole("button", { name: /Refuse/ }).click();
  await expect.poll(() => decisions.length).toBe(1);
  expect(decisions[0].decision).toBe("refuse");
});

test("a console section that fails says so and can retry", async ({ page }) => {
  let fail = true;
  await openApp(page, "admin", {
    overrides: {
      "GET /admin/console/audit": (route: Route) => (fail
        ? json(route, { detail: "The audit store is unavailable." }, 503)
        : json(route, { total: 0, page: 1, page_size: 25, actions: [], resource_types: [], events: [] })),
    },
  });
  await openTab(page, "Audit");
  await expect(page.getByRole("tabpanel")).toContainText("The audit store is unavailable.");
  fail = false;
  await page.getByRole("tabpanel").getByRole("button", { name: /Try again|Retry/ }).click();
  await expect(page.getByRole("tabpanel")).not.toContainText("The audit store is unavailable.");
});
