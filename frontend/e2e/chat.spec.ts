import { expect, test, type Route } from "@playwright/test";
import { ANSWER, CITATION, ESCALATED, JOB_ID, json, MESSAGE_ID, mockApi, openApp, SESSION_ID, openPro } from "./mock-api";

const ask = async (page: import("@playwright/test").Page, question: string) => {
  await page.getByLabel("Legal research question").fill(question);
  await page.keyboard.press("Enter");
};

test.describe("a Fast answer", () => {
  test("shows its citations, and a citation opens its passage", async ({ page }) => {
    await openApp(page, "citizen");
    await ask(page, "Can I report an offence by message?");
    await expect(page.locator(".assistant-message")).toContainText("officer in charge");
    const chip = page.getByRole("button", { name: `Preview source 1: ${CITATION.title}` });
    await chip.click();
    const preview = page.getByRole("region", { name: "Source preview" });
    await expect(preview).toContainText(CITATION.title);
    await expect(preview).toContainText("Pages 52–53");
    await page.getByRole("button", { name: "Close source preview" }).click();
    await expect(preview).toHaveCount(0);
  });

  test("records a rating, and says so when it cannot", async ({ page }) => {
    let refuse = false;
    await openApp(page, "citizen", { overrides: { "POST /feedback": (route: Route) => (refuse ? json(route, { detail: "no" }, 500) : json(route, { ok: true })) } });
    await ask(page, "A question");
    const helpful = page.getByRole("button", { name: "Mark answer helpful" });
    await helpful.click();
    await expect(helpful).toHaveAttribute("aria-pressed", "true");
    refuse = true;
    await page.getByRole("button", { name: "Mark answer not helpful" }).click();
    await expect(page.getByText("Your rating could not be saved.")).toBeVisible();
    await expect(helpful).toHaveAttribute("aria-pressed", "true");
  });

  test("a server failure reads as a failure and can be retried", async ({ page }) => {
    let fail = true;
    await openApp(page, "citizen", {
      overrides: { "POST /chat/query": (route: Route) => (fail ? json(route, { detail: "The model is not available." }, 503) : json(route, ANSWER)) },
    });
    await ask(page, "A question");
    await expect(page.locator("main, .auth-shell").getByRole("alert")).toContainText("The model is not available.");
    fail = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.locator(".assistant-message")).toContainText("officer in charge");
  });
});

test("the chat shell follows the chosen language; the answer stays in English", async ({ page }) => {
  await openApp(page, "citizen");
  await page.getByRole("button", { name: "हिन्दी" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByRole("button", { name: "चैट खोजें" })).toBeVisible();
  const input = page.getByRole("textbox", { name: "क़ानूनी प्रश्न" });
  await input.fill("A question");
  await page.keyboard.press("Enter");
  await expect(page.locator(".answer-lead")).toHaveAttribute("lang", "en");
  await expect(page.getByText("स्रोत", { exact: true })).toBeVisible();
});

test("settings and the conversation finder follow the language too", async ({ page }) => {
  await openApp(page, "citizen");
  await page.getByRole("button", { name: "తెలుగు" }).click();
  await page.getByRole("button", { name: "సెట్టింగ్‌లు" }).click();
  await expect(page.getByRole("dialog", { name: "సెట్టింగ్‌లు" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "చాట్‌లు వెతకండి" }).click();
  await expect(page.getByRole("dialog", { name: "మీ సంభాషణలు" })).toBeVisible();
});

test("a professional keeps English whatever was left in this browser", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("corpusil-language", "hi"));
  await openPro(page, "advocate");
  await expect(page.getByRole("button", { name: "Search chats" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test.describe("a Deep review", () => {
  const job = (status: string) => ({
    id: JOB_ID,
    status,
    progress: status === "succeeded" ? 100 : 40,
    stage_label: status === "running" ? "Checking each claim" : null,
    stage: null,
    error_code: null,
    error_message: null,
    result: status === "succeeded" ? { session_id: SESSION_ID, message_id: MESSAGE_ID, answer: "The finished review.", citations: [CITATION], confidence_score: 0.8, evidence_strength: "strong", section_confidence: [], intent: {}, agent_trace: [], timings_ms: {}, pipeline_metrics: [] } : null,
  });
  const conversation = { id: SESSION_ID, title: "A question", case_id: null, messages: [{ id: "00000000-0000-4000-8000-000000000099", role: "user", content: "A question", citations: [], confidence_score: null, created_at: "2026-11-05T09:00:00Z" }] };

  function server() {
    const state = { status: "running" };
    return {
      state,
      overrides: {
        "POST /chat/query": (route: Route) => json(route, ESCALATED),
        [`GET /jobs/${JOB_ID}`]: (route: Route) => json(route, job(state.status)),
        // No stream here: following falls back to polling, as behind a proxy that eats streams.
        [`GET /jobs/${JOB_ID}/events`]: (route: Route) => route.fulfill({ status: 503, body: "" }),
        [`GET /chat/sessions/${SESSION_ID}`]: (route: Route) => json(route, conversation),
        [`POST /jobs/${JOB_ID}/cancel`]: (route: Route) => { state.status = "cancelled"; return json(route, job("cancelled")); },
      } as Record<string, (route: Route) => unknown>,
    };
  }

  test("is picked up after a reload", async ({ page }) => {
    const backend = server();
    await openApp(page, "citizen", { overrides: backend.overrides });
    await ask(page, "A question");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    await page.reload();
    await expect(page.locator(".user-message")).toContainText("A question");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    backend.state.status = "succeeded";
    await expect(page.locator(".assistant-message")).toContainText("The finished review.");
    await page.reload();
    await expect(page.getByLabel("Legal research question")).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop response" })).toHaveCount(0);
  });

  test("a second tab finds it and does not follow it twice", async ({ context, page }) => {
    const backend = server();
    await openApp(page, "citizen", { overrides: backend.overrides });
    await ask(page, "A question");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();

    const second = await context.newPage();
    const streamsFromSecond: string[] = [];
    second.on("request", (request) => { if (request.url().endsWith("/events")) streamsFromSecond.push(request.url()); });
    await mockApi(second, { role: "citizen", overrides: backend.overrides });
    await second.goto("/");
    await expect(second.locator(".user-message")).toContainText("A question");
    await expect(second.getByRole("button", { name: "Stop response" })).toBeVisible();
    await second.waitForTimeout(1500);
    expect(streamsFromSecond).toEqual([]);

    backend.state.status = "succeeded";
    await expect(page.locator(".assistant-message")).toContainText("The finished review.");
    await expect(second.locator(".assistant-message")).toContainText("The finished review.");
    expect(streamsFromSecond).toEqual([]);
  });

  test("the second tab takes over if the first one closes", async ({ context, page }) => {
    const backend = server();
    await openApp(page, "citizen", { overrides: backend.overrides });
    await ask(page, "A question");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    const second = await context.newPage();
    await mockApi(second, { role: "citizen", overrides: backend.overrides });
    await second.goto("/");
    await expect(second.getByRole("button", { name: "Stop response" })).toBeVisible();
    await page.close();
    backend.state.status = "succeeded";
    await expect(second.locator(".assistant-message")).toContainText("The finished review.");
  });

  test("stopping cancels it on the server", async ({ page }) => {
    const backend = server();
    await openApp(page, "citizen", { overrides: backend.overrides });
    await ask(page, "A question");
    await page.getByRole("button", { name: "Stop response" }).click();
    await expect(page.getByText("Response stopped.")).toBeVisible();
    await expect.poll(() => backend.state.status).toBe("cancelled");
    await page.reload();
    await expect(page.getByRole("button", { name: "Stop response" })).toHaveCount(0);
  });

  test("a record pointing at a job that is gone opens a clean screen", async ({ page }) => {
    await page.addInitScript(([id, job, session]) => {
      window.localStorage.setItem(`corpusil.active-job.v1:${id}`, JSON.stringify({ jobId: job, sessionId: session, startedAt: 1 }));
    }, ["00000000-0000-4000-8000-000000000010", JOB_ID, SESSION_ID]);
    await openApp(page, "citizen");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Let’s make sense of the law.");
    await expect(page.locator("main, .auth-shell").getByRole("alert")).toHaveCount(0);
  });
});
