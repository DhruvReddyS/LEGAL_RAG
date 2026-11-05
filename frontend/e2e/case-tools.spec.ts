import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { expect, test, type Page, type Route } from "@playwright/test";
import { ANSWER, CASE_ID, json, mockApi, openApp } from "./mock-api";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const WIDTHS = [375, 1280];
const THEMES = ["paper", "ink"] as const;

async function expectAccessible(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).slice(0, 5).join(" | ")}`)).toEqual([]);
}

async function expectNoSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

const setTheme = (page: Page, theme: string) =>
  page.addInitScript((value) => window.localStorage.setItem("corpusil.site-theme", value), theme);

async function openCaseTool(page: Page, workspace: string, tool: RegExp) {
  const openNav = page.locator(".workspace-header .icon-button.lg\\:hidden");
  if (await openNav.isVisible()) await openNav.click();
  await page.locator(".feature-nav").getByRole("button", { name: workspace }).click();
  await page.getByRole("navigation", { name: "Case tools" }).getByRole("button", { name: tool }).click();
}

const emptyLists = {
  [`GET /cases/${CASE_ID}/documents/indexed`]: (route: Route) => json(route, { documents: [] }),
  [`GET /cases/${CASE_ID}/notes`]: (route: Route) => json(route, { notes: [] }),
};

test.describe("adding many files to a case", () => {
  test("each file gets its own outcome, and one failure does not stop the rest", async ({ page }) => {
    const order: string[] = [];
    let objects = 0;
    await openApp(page, "advocate", {
      overrides: {
        ...emptyLists,
        [`POST /cases/${CASE_ID}/storage/objects`]: (route: Route) => {
          objects += 1;
          order.push(`upload ${objects}`);
          if (objects === 2) return json(route, { detail: "Case documents must be between 1 byte and 25 MiB" }, 413);
          return json(route, { id: `00000000-0000-4000-8000-0000000000${10 + objects}` }, 201);
        },
        [`POST /cases/${CASE_ID}/storage/objects/00000000-0000-4000-8000-000000000011/index`]: (route: Route) => {
          order.push("index first");
          return json(route, { pages: 2, chunks: 5 }, 201);
        },
        [`POST /cases/${CASE_ID}/storage/objects/00000000-0000-4000-8000-000000000013/index`]: (route: Route) => {
          order.push("index third");
          return json(route, { pages: 1, chunks: 1 }, 201);
        },
      },
    });
    await openCaseTool(page, "Your cases", /Add evidence/);
    await page.locator('input[type="file"]').first().setInputFiles([
      { name: "first.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 a") },
      { name: "virus.exe", mimeType: "application/x-msdownload", buffer: Buffer.from("MZ") },
      { name: "second.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 b") },
      { name: "third.txt", mimeType: "text/plain", buffer: Buffer.from("plain") },
    ]);
    const queue = page.getByRole("region", { name: "Files being added" });
    await expect(queue.getByRole("status")).toContainText("4 of 4 finished, 2 failed");
    await expect(queue.locator('li[data-status="done"]')).toHaveCount(2);
    await expect(queue.locator("li", { hasText: "virus.exe" })).toContainText("Only PDF and TXT");
    await expect(queue.locator("li", { hasText: "second.pdf" })).toContainText("25 MiB");
    expect(order).toEqual(["upload 1", "index first", "upload 2", "upload 3", "index third"]);
    await expect(queue.getByRole("button", { name: "Retry second.pdf" })).toBeVisible();
    await expect(queue.getByRole("button", { name: "Retry virus.exe" })).toHaveCount(0);
    await expectAccessible(page);
  });

  test("files can be dropped, and the queue survives moving to another tool", async ({ page }) => {
    await openApp(page, "advocate", {
      overrides: {
        ...emptyLists,
        [`POST /cases/${CASE_ID}/storage/objects`]: (route: Route) => json(route, { id: "00000000-0000-4000-8000-000000000011" }, 201),
        [`POST /cases/${CASE_ID}/storage/objects/00000000-0000-4000-8000-000000000011/index`]: (route: Route) => json(route, { pages: 1, chunks: 1 }, 201),
      },
    });
    await openCaseTool(page, "Your cases", /Add evidence/);
    const transfer = await page.evaluateHandle(() => {
      const data = new DataTransfer();
      data.items.add(new File(["hello"], "dropped.txt", { type: "text/plain" }));
      return data;
    });
    await page.locator(".evidence-drop").dispatchEvent("drop", { dataTransfer: transfer });
    const queue = page.getByRole("region", { name: "Files being added" });
    await expect(queue.locator("li", { hasText: "dropped.txt" })).toHaveAttribute("data-status", "done");
    await page.getByRole("navigation", { name: "Case tools" }).getByRole("button", { name: /Case file/ }).click();
    await page.getByRole("navigation", { name: "Case tools" }).getByRole("button", { name: /Add evidence/ }).click();
    await expect(page.getByRole("region", { name: "Files being added" }).locator("li", { hasText: "dropped.txt" })).toBeVisible();
  });
});

test("the police case file saves as a Word file with a valid package", async ({ page }) => {
  const html = "<!doctype html><html><head><title>t</title><style>p{}</style></head><body><h1>State v. A &amp; B</h1><h2>1. Facts</h2><p>Text.</p><table><thead><tr><th>When</th></tr></thead><tbody><tr><td>Today</td></tr></tbody></table></body></html>";
  await openApp(page, "police", {
    overrides: {
      ...emptyLists,
      [`GET /cases/${CASE_ID}/police/case-file`]: (route: Route) => json(route, { case_id: CASE_ID, generated_at: "2026-11-05T10:00:00Z", included_witness_contact: false, html, missing_sections: [] }),
      [`GET /cases/${CASE_ID}/police/access-log`]: (route: Route) => json(route, { entries: [] }),
    },
  });
  await openCaseTool(page, "Investigations", /Court file/);
  await page.getByRole("button", { name: "Compile the case file" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save as Word" }).click()]);
  expect(download.suggestedFilename()).toBe("case-file-2026-11-05.docx");
  const bytes = await readFile(await download.path());
  expect(bytes.subarray(0, 4).toString("latin1")).toBe("PK\u0003\u0004");
  const text = bytes.toString("utf8");
  expect(text).toContain("[Content_Types].xml");
  expect(text).toContain("State v. A &amp; B");
  expect(text).toContain("<w:tbl>");
});

test.describe("case notes", () => {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      test(`create, edit and delete, at ${width}px in ${theme}`, async ({ page }) => {
        await setTheme(page, theme);
        await page.setViewportSize({ width, height: 800 });
        let notes: Record<string, unknown>[] = [];
        const NOTE_ID = "00000000-0000-4000-8000-000000000021";
        await openApp(page, "advocate", {
          overrides: {
            [`GET /cases/${CASE_ID}/documents/indexed`]: emptyLists[`GET /cases/${CASE_ID}/documents/indexed`],
            [`GET /cases/${CASE_ID}/notes`]: (route: Route) => json(route, { notes }),
            [`POST /cases/${CASE_ID}/notes`]: (route: Route) => {
              const body = route.request().postDataJSON().body;
              const note = { id: NOTE_ID, case_id: CASE_ID, body, created_at: "2026-11-05T10:00:00Z", updated_at: "2026-11-05T10:00:00Z" };
              notes = [note];
              return json(route, note, 201);
            },
            [`PUT /cases/${CASE_ID}/notes/${NOTE_ID}`]: (route: Route) => {
              const note = { ...notes[0], body: route.request().postDataJSON().body, updated_at: "2026-11-05T11:00:00Z" };
              notes = [note];
              return json(route, note);
            },
            [`DELETE /cases/${CASE_ID}/notes/${NOTE_ID}`]: (route: Route) => { notes = []; return route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": route.request().headers().origin ?? "*", "Access-Control-Allow-Credentials": "true" } }); },
          },
        });
        await openCaseTool(page, "Your cases", /Case file/);
        await expect(page.getByText("No notes on this case yet.")).toBeVisible();
        await page.getByLabel("New note").fill("Ask for the bail order copy");
        await page.getByRole("button", { name: "Add note" }).click();
        const list = page.locator(".case-notes-list");
        await expect(list).toContainText("Ask for the bail order copy");
        await expectAccessible(page);
        await expectNoSidewaysScroll(page);

        await list.getByRole("button", { name: "Edit" }).click();
        await page.getByLabel("Edit note").fill("Ask for the certified copy");
        await list.getByRole("button", { name: "Save" }).click();
        await expect(list).toContainText("Ask for the certified copy");
        await expect(list).toContainText("edited");

        await list.getByRole("button", { name: "Delete" }).click();
        await list.getByRole("button", { name: "Delete" }).click();
        await expect(page.getByText("No notes on this case yet.")).toBeVisible();
      });
    }
  }
});

const IPC = {
  query: "IPC 420", understood: true, act: "Indian Penal Code", section: "420",
  provisions: [{ title: "Indian Penal Code, 1860", act_name: "Indian Penal Code, 1860", section: "420", text: "Text of the earlier section.", page_start: 90, page_end: 90, source_url: null, jurisdiction: "India", currency_status: "superseded", superseded_by: "BNS", currency_basis: null }],
  counterparts: [{ from_code: "IPC", from_section: "420", to_code: "BNS", to_section: "318(4)", subject: "Cheating", ingredients_changed: true, note: null }],
};
const BNS = {
  query: "BNS 318(4)", understood: true, act: "Bharatiya Nyaya Sanhita", section: "318(4)",
  provisions: [{ title: "Bharatiya Nyaya Sanhita, 2023", act_name: "Bharatiya Nyaya Sanhita, 2023", section: "318", text: "Text of the later section.", page_start: 80, page_end: 80, source_url: null, jurisdiction: "India", currency_status: "in_force", superseded_by: null, currency_basis: null }],
  counterparts: [],
};
const lawOverrides = {
  "GET /law/lookup": (route: Route) => json(route, new URL(route.request().url()).searchParams.get("q")?.startsWith("BNS") ? BNS : IPC),
};

test.describe("old and new law side by side", () => {
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      test(`at ${width}px in ${theme}`, async ({ page }) => {
        await setTheme(page, theme);
        await page.setViewportSize({ width, height: 800 });
        await mockApi(page, { role: "advocate", overrides: lawOverrides });
        await page.goto("/law?q=IPC%20420");
        await page.getByRole("button", { name: /side by side/ }).click();
        const sides = page.locator(".law-compare-side");
        await expect(sides.nth(1)).toContainText("Text of the later section.");
        await expect(sides.nth(0)).toContainText("Text of the earlier section.");
        await expect(page.locator(".law-compare-head")).toContainText("Wording or ingredients changed. Read both.");
        const [first, second] = [await sides.nth(0).boundingBox(), await sides.nth(1).boundingBox()];
        if (width >= 900) expect(second!.x).toBeGreaterThan(first!.x + 100);
        else expect(second!.y).toBeGreaterThan(first!.y + 50);
        await expectAccessible(page);
        await expectNoSidewaysScroll(page);
        await page.getByRole("button", { name: "Close", exact: true }).click();
        await expect(page.locator(".law-compare")).toHaveCount(0);
      });
    }
  }

  test("a counterpart with no text says so, and the opened text stays", async ({ page }) => {
    await mockApi(page, { role: "advocate", overrides: { "GET /law/lookup": (route: Route) => json(route, new URL(route.request().url()).searchParams.get("q")?.startsWith("BNS") ? { ...BNS, provisions: [] } : IPC) } });
    await page.goto("/law?q=IPC%20420");
    await page.getByRole("button", { name: /side by side/ }).click();
    await expect(page.locator(".law-compare-side").nth(1)).toContainText("not held in the corpus");
    await expect(page.locator(".law-compare-side").nth(0)).toContainText("Text of the earlier section.");
  });
});

test.describe("browsing an Act", () => {
  const ACT = { id: "abc123", name: "Consumer Protection Act, 2019", section_count: 3 };

  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      test(`list, sections and opening one, at ${width}px in ${theme}`, async ({ page }) => {
        await setTheme(page, theme);
        await page.setViewportSize({ width, height: 800 });
        let calls = 0;
        const asked: string[] = [];
        await mockApi(page, {
          role: "advocate",
          overrides: {
            ...lawOverrides,
            "GET /law/acts": (route: Route) => {
              calls += 1;
              asked.push(new URL(route.request().url()).searchParams.get("name") ?? "");
              return calls === 1 ? json(route, { ready: false, acts: [], total: 0 }) : json(route, { ready: true, acts: [ACT], total: 1 });
            },
            "GET /law/acts/abc123/sections": (route: Route) => json(route, {
              ready: true, id: ACT.id, name: ACT.name,
              sections: ["2", "2A", "10"].map((section) => ({ section, citation: `Section ${section} of ${ACT.name}` })),
            }),
          },
        });
        await page.goto("/law");
        await page.waitForTimeout(400);
        expect(calls, "a visitor reading the page starts no scroll of the corpus").toBe(0);
        const field = page.getByLabel("Name of the Act");
        await field.fill("consumer");
        await expect(page.getByText("is being prepared")).toBeVisible();
        await page.getByRole("button", { name: new RegExp(ACT.name) }).click();
        const sections = page.locator(".law-browse-sections button");
        await expect(sections).toHaveText(["2", "2A", "10"]);
        await expectAccessible(page);
        await expectNoSidewaysScroll(page);
        await page.getByRole("button", { name: "Section 2 of Consumer Protection Act, 2019" }).click();
        await expect(page).toHaveURL(/q=Section%202%20of%20Consumer/);
        expect(asked).toContain("consumer");
      });
    }
  }
});

test.describe("follow-up questions", () => {
  test("choosing one fills the composer and sends nothing", async ({ page }) => {
    let queries = 0;
    await openApp(page, "advocate", { overrides: { "POST /chat/query": (route: Route) => { queries += 1; return json(route, ANSWER); } } });
    await page.getByLabel("Legal research question").fill("A question");
    await page.keyboard.press("Enter");
    const region = page.getByRole("region", { name: "You could ask next" });
    await expect(region.getByRole("button")).toHaveCount(3);
    await region.getByRole("button").first().click();
    const composer = page.getByLabel("Legal research question");
    await expect(composer).toHaveValue(/\?$/);
    await expect(composer).toBeFocused();
    expect(queries).toBe(1);
    await expectAccessible(page);
  });

  test("a citizen sees them in their language", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("corpusil-language", "hi"));
    await mockApi(page, { role: "citizen" });
    await page.goto("/");
    await page.locator(".composer textarea").fill("A question");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "आप आगे यह पूछ सकते हैं" }).getByRole("button").first()).toBeVisible();
    await page.setViewportSize({ width: 375, height: 800 });
    await expectNoSidewaysScroll(page);
  });
});

test.describe("browser reminders", () => {
  const fakeNotification = (permission: string) => {
    const made: { title: string; body?: string }[] = [];
    (window as unknown as { __made: typeof made }).__made = made;
    class FakeNotification {
      static permission = permission;
      static requestPermission = async () => {
        FakeNotification.permission = "granted";
        (window as unknown as { __asked: boolean }).__asked = true;
        return "granted";
      };
      constructor(title: string, options?: { body?: string }) { made.push({ title, body: options?.body }); }
    }
    (window as unknown as { Notification: unknown }).Notification = FakeNotification;
  };
  const made = (page: Page) => page.evaluate(() => (window as unknown as { __made: { title: string; body?: string }[] }).__made);
  const DEADLINES = {
    "GET /citizen/matter/deadlines": (route: Route) => json(route, {
      today: "2026-11-05",
      items: [
        { id: "d1", title: "Secret hearing against Mr. X", status: "overdue", completed_at: null, due_on: "2026-11-01", days_left: -4, remind_days_before: 1, notes: null, source: "user", provision_label: null, created_at: "2026-10-01T00:00:00Z" },
        { id: "d2", title: "Another private title", status: "due_today", completed_at: null, due_on: "2026-11-05", days_left: 0, remind_days_before: 1, notes: null, source: "user", provision_label: null, created_at: "2026-10-01T00:00:00Z" },
      ],
    }),
  };

  test("once granted: one notification, with a count and no details, not repeated on reload", async ({ page }) => {
    await page.addInitScript(fakeNotification, "granted");
    await openApp(page, "citizen", { overrides: DEADLINES });
    await expect.poll(() => made(page)).toHaveLength(1);
    const [notification] = await made(page);
    expect(notification.title).toBe("Corpusil");
    expect(notification.body).toBe("2 deadlines need attention.");
    await page.reload();
    await page.getByLabel("Legal research question").waitFor();
    await page.waitForTimeout(500);
    expect(await made(page)).toHaveLength(0);
  });

  test("permission is asked only from the button in Settings", async ({ page }) => {
    await page.addInitScript(fakeNotification, "default");
    let deadlineCalls = 0;
    await openApp(page, "advocate", { overrides: { "GET /advocate/calendar": (route: Route) => { deadlineCalls += 1; return json(route, { today: "2026-11-05", events: [{ id: "e1", state: "due_today", completed: false }] }); } } });
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => (window as unknown as { __asked?: boolean }).__asked)).toBeUndefined();
    expect(deadlineCalls, "no request before permission").toBe(0);
    await page.getByRole("button", { name: "Settings" }).click();
    await page.getByRole("button", { name: "Turn on" }).click();
    await expect(page.getByText(/^On\. A count is shown/)).toBeVisible();
    await expect.poll(() => made(page)).toHaveLength(1);
    expect((await made(page))[0].body).toBe("1 deadline needs attention.");
    await expectAccessible(page);
  });

  test("a page with no Notification support does nothing, and says so in Settings", async ({ page }) => {
    await page.addInitScript(() => { delete (window as unknown as { Notification?: unknown }).Notification; });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let deadlineCalls = 0;
    await openApp(page, "police", { overrides: { "GET /police/deadlines": (route: Route) => { deadlineCalls += 1; return json(route, { rows: [] }); } } });
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(page.getByText("This browser cannot show them.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Turn on" })).toHaveCount(0);
    expect(deadlineCalls).toBe(0);
    expect(errors).toEqual([]);
  });
});
