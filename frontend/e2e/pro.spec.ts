import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { ANSWER, API, CASE_ID, CITATION, ESCALATED, JOB_ID, json, MESSAGE_ID, mockApi, openPro, SECOND_CASE_ID, SESSION_ID } from "./mock-api";

const ROLES = ["police", "advocate"] as const;
const caseUrl = (id: string, rest = "") => `/?s=case&case=${id}${rest}`;
const nav = (page: Page) => page.getByRole("navigation", { name: "Main sections" });
const tabs = (page: Page) => page.getByRole("navigation", { name: "Case sections" });

for (const role of ROLES) {
  const cases = role === "police" ? "Investigations" : "Cases";
  const filesTab = role === "police" ? "Files and evidence" : "Files";

  test.describe(`${role}`, () => {
    test("signs in to a dashboard, not a chat box", async ({ page }) => {
      await mockApi(page, { role: null, signsInAs: role });
      await page.goto("/?signin");
      await page.getByLabel("Email").fill(`${role}@example.test`);
      await page.getByLabel("Password", { exact: true }).fill("password-for-tests");
      await page.getByRole("button", { name: "Sign in" }).last().click();
      await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
      await expect(page.getByLabel("Legal research question")).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
      await expect(page.getByText(role === "police" ? "Produce the arrested person before the Magistrate" : "File the appeal").first()).toBeVisible();
    });

    test("a case has its own page: tabs, reload, a second case, and back", async ({ page }) => {
      await openPro(page, role);
      await nav(page).getByRole("link", { name: cases }).click();
      await expect(page).toHaveURL(/s=cases/);
      await page.getByRole("link", { name: "State v. Test" }).click();

      await expect(page.getByRole("heading", { level: 1, name: "State v. Test" })).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`case=${CASE_ID}`));
      await expect(page.getByText(role === "police" ? "Police investigation" : "Advocate case")).toBeVisible();

      await tabs(page).getByRole("link", { name: filesTab }).click();
      await expect(page.getByRole("button", { name: /first-case-statement.pdf/ })).toBeVisible();
      await tabs(page).getByRole("link", { name: "Timeline" }).click();
      await expect(page.getByText("An event in the first case.")).toBeVisible();

      await page.reload();
      await expect(page.getByRole("heading", { level: 1, name: "State v. Test" })).toBeVisible();
      await expect(tabs(page).getByRole("link", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
      await expect(page.getByText("An event in the first case.")).toBeVisible();

      // Into the second case. Nothing of the first may still be in the page, even hidden.
      await nav(page).getByRole("link", { name: cases }).click();
      await page.getByRole("link", { name: "State v. Second" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "State v. Second" })).toBeVisible();
      await tabs(page).getByRole("link", { name: "Timeline" }).click();
      await expect(page.getByText("An event in the second case.")).toBeVisible();
      await expect(page.locator("body")).not.toContainText("An event in the first case.");
      await tabs(page).getByRole("link", { name: filesTab }).click();
      await expect(page.getByRole("button", { name: /second-case-order.pdf/ })).toBeVisible();
      await expect(page.locator("body")).not.toContainText("first-case-statement.pdf");

      // Back retraces the steps: the second case's tabs, then the list.
      await page.goBack();
      await expect(tabs(page).getByRole("link", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
      await page.goBack();
      await expect(tabs(page).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
      await page.goBack();
      await expect(page.getByRole("heading", { level: 1, name: cases })).toBeVisible();
      await page.goForward();
      await expect(page.getByRole("heading", { level: 1, name: "State v. Second" })).toBeVisible();
    });

    test("what is typed in a tool survives moving between tabs, and not into another case", async ({ page }) => {
      await page.goto("about:blank");
      await openPro(page, role, caseUrl(CASE_ID, role === "police" ? "&tab=drafts" : "&tab=strategy"));
      const box = page.getByLabel(role === "police" ? "What is known so far" : "The case as you understand it");
      await box.fill("Typed about the first case only.");
      await tabs(page).getByRole("link", { name: "Overview" }).click();
      await nav(page).getByRole("link", { name: "Dashboard" }).click();
      await page.goBack();
      await page.goBack();
      await expect(box).toHaveValue("Typed about the first case only.");
      await nav(page).getByRole("link", { name: cases }).click();
      await page.getByRole("link", { name: "State v. Second" }).click();
      await tabs(page).getByRole("link", { name: role === "police" ? "Drafts" : "Strategy" }).click();
      await expect(page.getByLabel(role === "police" ? "What is known so far" : "The case as you understand it")).toHaveValue("");
    });

    test("a new person sees first steps, and one action makes a case", async ({ page }) => {
      const noun = role === "police" ? "investigation" : "case";
      const made = { id: "00000000-0000-4000-8000-000000000077", owner_id: "x", role_type: role, title: "A brand new matter", status: "open", created_at: "2026-11-05T09:00:00Z" };
      await openPro(page, role, "/", {
        noCases: true,
        overrides: { "POST /cases": (route: Route) => json(route, made) },
      });
      await expect(page.getByRole("heading", { name: "Get started in three steps" })).toBeVisible();
      await page.getByRole("button", { name: `New ${noun}` }).first().click();
      const dialog = page.getByRole("dialog", { name: `New ${noun}` });
      await dialog.getByRole("textbox").fill("A brand new matter");
      await dialog.getByRole("button", { name: `Create ${noun}` }).click();
      await expect(page.getByRole("heading", { level: 1, name: "A brand new matter" })).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`case=${made.id}`));
    });

    test("a failed read says so, and can be tried again", async ({ page }) => {
      let refuse = true;
      await openPro(page, role, "/", {
        overrides: {
          "GET /cases": (route: Route) => (refuse
            ? json(route, { detail: "down" }, 500)
            : json(route, { cases: [{ id: CASE_ID, owner_id: "x", role_type: role, title: "State v. Test", status: "open", created_at: "2026-11-05T09:00:00Z" }], total: 1 })),
        },
      });
      const alert = page.getByRole("alert").filter({ hasText: "could not be read" });
      await expect(alert).toBeVisible();
      refuse = false;
      await alert.getByRole("button", { name: "Try again" }).click();
      await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
    });

    test("a link to a case not in the person's list reads nothing of it", async ({ page }) => {
      const stranger = "00000000-0000-4000-8000-00000000abcd";
      const asked: string[] = [];
      page.on("request", (request) => { if (request.url().startsWith(API) && request.url().includes(stranger)) asked.push(request.url()); });
      await openPro(page, role, caseUrl(stranger, "&tab=files"));
      await expect(page.getByRole("heading", { name: /cannot be opened/ })).toBeVisible();
      expect(asked).toEqual([]);
    });

    test("law-only chat and case chat stay apart", async ({ page }) => {
      const bodies: { query: string; case_id: unknown }[] = [];
      const chat = (route: Route) => {
        bodies.push(route.request().postDataJSON());
        return json(route, ANSWER);
      };
      await openPro(page, role, "/?s=research", { overrides: { "POST /chat/query": chat } });
      await expect(page.getByText("Law only", { exact: true })).toBeVisible();
      await expect(page.getByLabel("Knowledge scope")).toHaveCount(0);
      await page.getByLabel("Legal research question").fill("A law question");
      await page.keyboard.press("Enter");
      await expect(page.getByText("may be given to an officer")).toBeVisible();
      expect(bodies[0].case_id ?? null).toBeNull();

      // The law-only conversation does not follow into a case.
      await page.goto(caseUrl(CASE_ID, "&tab=ask"));
      await expect(page.getByRole("heading", { name: "Ask about State v. Test" })).toBeVisible();
      await page.getByLabel("Legal research question").fill("A case question");
      await page.keyboard.press("Enter");
      await expect(page.getByText("may be given to an officer")).toBeVisible();
      expect(bodies[1].case_id).toBe(CASE_ID);

      // Nor does the case conversation follow to Research or into another case.
      await nav(page).getByRole("link", { name: "Research" }).click();
      await expect(page.getByRole("heading", { name: "What would you like to research?" })).toBeVisible();
      await expect(page.locator("body")).not.toContainText("A case question");
      await page.goto(caseUrl(SECOND_CASE_ID, "&tab=ask"));
      await expect(page.getByRole("heading", { name: "Ask about State v. Second" })).toBeVisible();
      await expect(page.locator("body")).not.toContainText("A case question");
    });

    test("reloading a case's Ask tab keeps the open conversation, and only its own", async ({ page }) => {
      const stored = (caseId: string | null) => ({
        id: SESSION_ID, title: "A case question", case_id: caseId, pinned: false, created_at: "2026-11-05T09:00:00Z", updated_at: "2026-11-05T09:00:00Z",
        messages: [
          { id: "11111111-1111-4111-8111-111111111111", role: "user", content: "A case question", citations: [], created_at: "2026-11-05T09:00:00Z" },
          { id: MESSAGE_ID, role: "assistant", content: "The stored answer survives a reload.", citations: [], created_at: "2026-11-05T09:00:01Z" },
        ],
      });
      let scope: string | null = CASE_ID;
      let missing = false;
      await openPro(page, role, caseUrl(CASE_ID, "&tab=ask"), {
        overrides: {
          [`GET /chat/sessions/${SESSION_ID}`]: (route: Route) => missing ? json(route, { detail: "Not found" }, 404) : json(route, stored(scope)),
        },
      });
      await page.getByLabel("Legal research question").fill("A case question");
      await page.keyboard.press("Enter");
      await expect(page.getByText("may be given to an officer")).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`chat=${SESSION_ID}`));

      await page.reload();
      await expect(page.getByText("The stored answer survives a reload.")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1, name: "State v. Test" })).toBeVisible();

      // A conversation from elsewhere is not shown under this case.
      scope = null;
      await page.goto(caseUrl(SECOND_CASE_ID, `&tab=ask&chat=${SESSION_ID}`));
      await expect(page.getByRole("heading", { name: "Ask about State v. Second" })).toBeVisible();
      await expect(page.locator("body")).not.toContainText("The stored answer survives");
      await expect(page).not.toHaveURL(/chat=/);

      // Someone else's, or a deleted one, opens as an empty chat.
      missing = true;
      await page.goto(caseUrl(CASE_ID, `&tab=ask&chat=${SESSION_ID}`));
      await expect(page.getByRole("heading", { name: "Ask about State v. Test" })).toBeVisible();
      await expect(page).not.toHaveURL(/chat=/);
    });

    test("nothing overflows a phone, and the drawer holds the navigation", async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 800 });
      await openPro(page, role);
      for (const path of ["/", "/?s=cases", caseUrl(CASE_ID), caseUrl(CASE_ID, "&tab=files"), caseUrl(CASE_ID, "&tab=ask"), "/?s=deadlines", "/?s=drafts", "/?s=research", "/?s=law", "/?s=help"]) {
        await page.goto(path);
        await page.locator(".pro-page, .pro-case, .pro-law").first().waitFor();
        await page.waitForTimeout(250);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), path).toBe(0);
      }
      await page.goto("/");
      const open = page.getByRole("button", { name: "Open navigation" });
      await open.click();
      await expect(page.getByRole("button", { name: "Close navigation" })).toBeFocused();
      await nav(page).getByRole("link", { name: "Drafts" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Drafts" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Close navigation" })).toBeHidden();
    });
  });
}

test("the two roles arrange a case differently", async ({ browser }) => {
  const labels = async (role: "police" | "advocate") => {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    await openPro(page, role, caseUrl(CASE_ID));
    await tabs(page).waitFor();
    const found = await tabs(page).getByRole("link").allInnerTexts();
    await context.close();
    return found;
  };
  expect(await labels("police")).toEqual(["Overview", "Timeline and people", "Files and evidence", "Deadlines and compliance", "Drafts", "Tools", "Notes", "Ask"]);
  expect(await labels("advocate")).toEqual(["Overview", "Timeline and people", "Files", "Dates", "Strategy", "Authorities", "Drafts", "Notes", "Ask"]);
});

test("the police tools are all reachable, and each names itself", async ({ page }) => {
  await openPro(page, "police", caseUrl(CASE_ID, "&tab=files"));
  await page.getByRole("navigation", { name: "Files and evidence tools" }).getByRole("link", { name: "Witnesses" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Witnesses" })).toBeVisible();
  await expect(page).toHaveURL(/tool=witnesses/);
  await tabs(page).getByRole("link", { name: "Deadlines and compliance" }).click();
  await page.getByRole("navigation", { name: "Deadlines and compliance tools" }).getByRole("link", { name: "Case diary" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Case diary" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { level: 2, name: "Case diary" })).toBeVisible();
});

test("the advocate tools are all reachable, and each names itself", async ({ page }) => {
  await openPro(page, "advocate", caseUrl(CASE_ID, "&tab=strategy&tool=bail"));
  await expect(page.getByRole("heading", { level: 2, name: "Bail" })).toBeVisible();
  await tabs(page).getByRole("link", { name: "Authorities" }).click();
  await page.getByRole("navigation", { name: "Authorities tools" }).getByRole("link", { name: "Treatment check" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Treatment check" })).toBeVisible();
  await tabs(page).getByRole("link", { name: "Dates" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Hearings and limitation" })).toBeVisible();
});

test("a case's Dates tab shows that case's dates and no other's", async ({ page }) => {
  await openPro(page, "advocate", caseUrl(CASE_ID, "&tab=dates"));
  await expect(page.getByRole("heading", { level: 2, name: "Hearings and limitation" })).toBeVisible();
  await expect(page.getByText("Arguments on bail")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("Framing of charges");
});

test("each chat is listed under its own scope, and opens there", async ({ page }) => {
  const row = (id: string, title: string, caseId: string | null) => ({ id, title, updated_at: "2026-11-05T09:00:00Z", last_message_preview: null, message_count: 2, case_id: caseId, pinned: false, matter: null });
  const lawChat = row(SESSION_ID, "A law-only chat", null);
  const caseChat = row(MESSAGE_ID, "A chat about the case", CASE_ID);
  await openPro(page, "police", "/?s=research", {
    overrides: {
      "GET /history/sessions": (route: Route) => json(route, { items: [lawChat, caseChat], next_cursor: null }),
      [`GET /chat/sessions/${MESSAGE_ID}`]: (route: Route) => json(route, { id: MESSAGE_ID, title: caseChat.title, case_id: CASE_ID, messages: [{ id: "00000000-0000-4000-8000-000000000098", role: "user", content: "Asked inside the case", citations: [], confidence_score: null, created_at: "2026-11-05T09:00:00Z" }] }),
    },
  });
  await expect(page.getByRole("button", { name: "A law-only chat", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "A chat about the case", exact: true })).toHaveCount(0);
  await page.goto(caseUrl(CASE_ID));
  await page.locator("[aria-labelledby='ov-chats']").getByRole("button", { name: /A chat about the case/ }).click();
  await expect(page).toHaveURL(/tab=ask/);
  await expect(page.getByText("Asked inside the case")).toBeVisible();
  await expect(page.getByRole("button", { name: "A law-only chat", exact: true })).toHaveCount(0);
});

test("a supervisor gets the unit, and an officer does not", async ({ page }) => {
  await openPro(page, "police");
  await expect(nav(page).getByRole("link", { name: "Dashboard" })).toBeVisible();
  await expect(nav(page).getByRole("link", { name: "Unit supervision" })).toHaveCount(0);
  await page.unrouteAll();
  await mockApi(page, {
    role: "police",
    overrides: {
      "GET /police/my-units": (route: Route) => json(route, { units: [{ unit_id: "unit-1", unit_name: "North Range", my_role: "supervisor", supervisors: [] }] }),
      "GET /police/supervision/units/unit-1": (route: Route) => json(route, { unit_name: "North Range", counts: { overdue: 2 }, compliance: {}, cases: [], officer_count: 3, imminent_hours: 48, evaluated_at: "2026-11-05T09:00:00Z" }),
    },
  });
  await page.reload();
  await expect(nav(page).getByRole("link", { name: "Unit supervision" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Unit supervision" })).toBeVisible();
});

test("signed out, a link to a case goes to the landing page and reads nothing", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (request) => { if (request.url().startsWith(API) && request.url().includes(`/cases/${CASE_ID}`)) asked.push(request.url()); });
  await mockApi(page, { role: null });
  await page.goto(caseUrl(CASE_ID));
  await expect(page).toHaveURL(/\/welcome/);
  expect(asked).toEqual([]);
});

test("the keyboard moves through the navigation and into a case", async ({ page }) => {
  await openPro(page, "advocate", "/?s=cases");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.getByRole("link", { name: "State v. Test" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "State v. Test" })).toBeVisible();
  // Arriving moves the keyboard to the new screen.
  await expect(page.locator("#pro-main")).toBeFocused();
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toHaveRole("link");
  expect(await focused.evaluate((node) => getComputedStyle(node).outlineStyle)).toBe("solid");
});

test.describe("a Deep review keeps its place", () => {
  const job = (status: string) => ({
    id: JOB_ID, status, progress: status === "succeeded" ? 100 : 40, stage_label: status === "running" ? "Checking each claim" : null, stage: null, error_code: null, error_message: null,
    result: status === "succeeded" ? { session_id: SESSION_ID, message_id: MESSAGE_ID, answer: "The finished review.", citations: [CITATION], confidence_score: 0.8, evidence_strength: "strong", section_confidence: [], intent: {}, agent_trace: [], timings_ms: {}, pipeline_metrics: [] } : null,
  });
  const conversation = (caseId: string | null) => ({ id: SESSION_ID, title: "A question", case_id: caseId, messages: [{ id: "00000000-0000-4000-8000-000000000099", role: "user", content: "A question", citations: [], confidence_score: null, created_at: "2026-11-05T09:00:00Z" }] });
  function server(caseId: string | null) {
    const state = { status: "running" };
    return {
      state,
      overrides: {
        "POST /chat/query": (route: Route) => json(route, ESCALATED),
        [`GET /jobs/${JOB_ID}`]: (route: Route) => json(route, job(state.status)),
        [`GET /jobs/${JOB_ID}/events`]: (route: Route) => route.fulfill({ status: 503, body: "" }),
        [`GET /chat/sessions/${SESSION_ID}`]: (route: Route) => json(route, conversation(caseId)),
      } as Record<string, (route: Route) => unknown>,
    };
  }

  test("picked up after a reload on Research", async ({ page }) => {
    const backend = server(null);
    await openPro(page, "police", "/?s=research", { overrides: backend.overrides });
    await page.getByLabel("Legal research question").fill("A question");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    backend.state.status = "succeeded";
    await expect(page.getByText("The finished review.")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("heading", { level: 1, name: "Research" })).toBeVisible();
  });

  test("picked up in its own case, and followed from elsewhere", async ({ page }) => {
    const backend = server(CASE_ID);
    await openPro(page, "advocate", caseUrl(CASE_ID, "&tab=ask"), { overrides: backend.overrides });
    await page.getByLabel("Legal research question").fill("A question");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();

    // Reloaded on the dashboard: the work goes on, and the way back is offered.
    await page.goto("/");
    const strip = page.getByRole("status").filter({ hasText: "still being prepared" });
    await expect(strip).toBeVisible();
    await strip.getByRole("link", { name: "Open it" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "State v. Test" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();

    // On a different chat screen it is neither shown there nor abandoned.
    await nav(page).getByRole("link", { name: "Research" }).click();
    await expect(page.getByRole("link", { name: "Open that chat" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("A question");
    await page.getByRole("link", { name: "Open that chat" }).click();
    backend.state.status = "succeeded";
    await expect(page.getByText("The finished review.")).toBeVisible({ timeout: 20_000 });
  });
});

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function expectClean(page: Page) {
  // A fade-in is measured at its end state: mid-fade, every colour reads as low contrast.
  await page.evaluate(() => Promise.all(document.getAnimations().filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity).map((animation) => animation.finished.catch(() => undefined))));
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).slice(0, 5).join(" | ")}`)).toEqual([]);
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("body *"))
    .filter((element) => Array.from(element.childNodes).some((node) => node.nodeType === 3 && (node.textContent ?? "").trim()))
    .filter((element) => element.getClientRects().length && parseFloat(getComputedStyle(element).fontSize) < 12)
    .map((element) => `${element.tagName} ${getComputedStyle(element).fontSize}: ${(element.textContent ?? "").slice(0, 30)}`));
  expect(small).toEqual([]);
  const unnamed = await page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>("input,textarea,select,button"))
    .filter((element) => element.getClientRects().length)
    .filter((element) => {
      const field = element as HTMLInputElement;
      if (element.getAttribute("aria-label") || element.getAttribute("aria-labelledby")) return false;
      return element.tagName === "BUTTON" ? !element.innerText.trim() : !field.labels?.length;
    })
    .map((element) => element.outerHTML.slice(0, 120)));
  expect(unnamed).toEqual([]);
}

const SCREENS = {
  dashboard: "/",
  cases: "/?s=cases",
  overview: caseUrl(CASE_ID),
  timeline: caseUrl(CASE_ID, "&tab=timeline"),
  files: caseUrl(CASE_ID, "&tab=files"),
  ask: caseUrl(CASE_ID, "&tab=ask"),
  deadlines: "/?s=deadlines",
  drafts: "/?s=drafts",
  research: "/?s=research",
  help: "/?s=help",
};

for (const theme of ["paper", "ink"] as const) {
  for (const role of ROLES) {
    for (const [name, path] of Object.entries(SCREENS)) {
      test(`accessibility: ${role} ${name}, ${theme}`, async ({ page }) => {
        await page.addInitScript((value) => window.localStorage.setItem("corpusil.site-theme", value), theme);
        await openPro(page, role, path);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await page.getByRole("heading", { level: 1 }).first().waitFor();
        await page.locator("[role='status'].pro-skeleton").first().waitFor({ state: "detached" }).catch(() => undefined);
        await page.waitForTimeout(400);
        await expectClean(page);
      });
    }
  }
}

test("accessibility: a new person's dashboard, and the new case dialog", async ({ page }) => {
  await openPro(page, "police", "/", { noCases: true });
  await page.getByRole("heading", { name: "Get started in three steps" }).waitFor();
  await expectClean(page);
  await page.getByRole("button", { name: "New investigation" }).first().click();
  await expect(page.getByRole("dialog", { name: "New investigation" })).toBeVisible();
  await expectClean(page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("a supervisor reloading the unit screen sees the unit, not Not Found", async ({ page }) => {
  const asked: string[] = [];
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await openPro(page, "police", "/?s=unit", {
    overrides: {
      "GET /police/my-units": async (route: Route) => {
        await held;
        return json(route, { units: [{ unit_id: "unit-1", unit_name: "North Range", my_role: "supervisor", supervisors: [] }] });
      },
      "GET /police/supervision/units/unit-1": (route: Route) => {
        asked.push(route.request().url());
        return json(route, { unit_name: "North Range", counts: { overdue: 2 }, compliance: {}, cases: [{ case_id: CASE_ID, title: "State v. Test", officer_name: "An Officer", has_facts: true, counts: { overdue: 1 }, compliance: {} }], officer_count: 3, imminent_hours: 48 });
      },
    },
  });
  // Still reading: this must not claim they supervise nothing.
  await expect(page.getByText("You do not supervise a unit")).toHaveCount(0);
  release();
  await expect(page.getByLabel("North Range at a glance")).toBeVisible();
  await expect(page.getByText("Not Found")).toHaveCount(0);
  await expect(page.getByText("1 needs attention")).toBeVisible();
  expect(asked.length).toBeGreaterThan(0);
});

test("a changed law is announced on the dashboard, and goes once it is read", async ({ page }) => {
  let read = false;
  const notice = { id: "n-1", document_title: "An Old Act", previous_status: "in_force", current_status: "superseded", superseded_by: "A New Act", effective: "2024-07-01", basis: null, conversation_id: SESSION_ID, conversation_title: "A question", created_at: "2026-11-05T09:00:00Z", read_at: null };
  await openPro(page, "advocate", "/", {
    overrides: {
      "GET /account/law-changes": (route: Route) => json(route, { unread: read ? 0 : 1, notices: read ? [] : [notice] }),
      "POST /account/law-changes/n-1/read": (route: Route) => { read = true; return route.fulfill({ status: 204 }); },
    },
  });
  const strip = page.getByRole("status").filter({ hasText: "The law behind a saved answer has changed" });
  await expect(strip).toBeVisible();
  await strip.getByRole("button", { name: "See what changed" }).click();
  const dialog = page.getByRole("dialog", { name: "Account and privacy" });
  await expect(dialog).toContainText("An Old Act");
  await dialog.getByRole("button", { name: "Mark as read" }).click();
  await dialog.getByRole("button", { name: "Close account and privacy" }).click();
  await expect(page.getByText("The law behind a saved answer has changed")).toHaveCount(0);
});
