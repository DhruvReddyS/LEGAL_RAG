import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { CASE_ID, mockApi, openApp, openPro, type Role } from "./mock-api";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function expectNoViolations(page: Page) {
  // A fade-in is measured at its end state: mid-fade, every colour reads as low contrast.
  await page.evaluate(() => Promise.all(document.getAnimations().filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity).map((animation) => animation.finished.catch(() => undefined))));
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(violations.map((item) => `${item.id}: ${item.nodes.map((node) => node.target.join(" ")).slice(0, 5).join(" | ")}`)).toEqual([]);
}

/** Text anyone has to read is at least 12px. */
async function expectReadableText(page: Page) {
  const small = await page.evaluate(() => Array.from(document.querySelectorAll("body *"))
    .filter((element) => Array.from(element.childNodes).some((node) => node.nodeType === 3 && (node.textContent ?? "").trim()))
    .filter((element) => element.getClientRects().length && parseFloat(getComputedStyle(element).fontSize) < 12)
    .map((element) => `${element.tagName} ${getComputedStyle(element).fontSize}: ${(element.textContent ?? "").slice(0, 30)}`));
  expect(small).toEqual([]);
}

for (const theme of ["paper", "ink"] as const) {
  test.describe(`${theme} theme`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((value) => window.localStorage.setItem("corpusil.site-theme", value), theme);
    });

    for (const path of ["/welcome", "/help", "/rights", "/law", "/?signin"]) {
      test(`public ${path}`, async ({ page }) => {
        await mockApi(page, { role: null });
        await page.goto(path);
        await expect(page.getByRole("heading").first()).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expectNoViolations(page);
        await expectReadableText(page);
      });
    }

    // Police and advocate have a screen-by-screen sweep of their own in pro.spec.ts.
    for (const role of ["citizen", "admin"] as Role[]) {
      test(`${role} chat and workspace`, async ({ page }) => {
        await openApp(page, role);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expectNoViolations(page);
        await page.locator(".feature-nav button").first().click();
        await page.waitForTimeout(500);
        await expectNoViolations(page);
        await expectReadableText(page);
      });
    }
  });
}

test("the answer view has no violations", async ({ page }) => {
  await openApp(page, "citizen");
  await page.getByLabel("Legal research question").fill("A question");
  await page.keyboard.press("Enter");
  await page.locator(".assistant-message").waitFor();
  await expectNoViolations(page);
  await expectReadableText(page);
});

test("every control has a programmatic name", async ({ page }) => {
  await openPro(page, "advocate", `/?s=case&case=${CASE_ID}&tab=strategy`);
  await page.getByRole("navigation", { name: "Strategy tools" }).waitFor();
  const unnamed = await page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>("input,textarea,select,button"))
    .filter((element) => element.getClientRects().length)
    .filter((element) => {
      const field = element as HTMLInputElement;
      if (element.getAttribute("aria-label") || element.getAttribute("aria-labelledby")) return false;
      return element.tagName === "BUTTON" ? !element.innerText.trim() : !field.labels?.length;
    })
    .map((element) => element.outerHTML.slice(0, 120)));
  expect(unnamed).toEqual([]);
});

test.describe("dialogs", () => {
  const dialogs: { name: string; open: (page: Page) => Promise<unknown>; title: string }[] = [
    { name: "settings", title: "Settings", open: (page) => page.getByRole("button", { name: "Settings" }).click() },
    { name: "search chats", title: "Your conversations", open: (page) => page.getByRole("button", { name: "Search chats" }).click() },
    { name: "guide", title: "Turn a confusing situation into a clear question.", open: (page) => page.getByRole("button", { name: "Getting started" }).click() },
    { name: "attachment", title: "A little context goes a long way.", open: (page) => page.getByRole("button", { name: "Attach a document or image" }).click() },
  ];

  for (const { name, open, title } of dialogs) {
    test(`${name} traps focus, closes on Escape and gives focus back`, async ({ page }) => {
      await openApp(page, "citizen");
      await open(page);
      const dialog = page.getByRole("dialog", { name: title });
      await expect(dialog).toBeVisible();
      await expectNoViolations(page);
      for (let press = 0; press < 25; press += 1) {
        await page.keyboard.press("Tab");
        expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
      }
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      expect(await page.evaluate(() => document.activeElement?.tagName)).toBe("BUTTON");
    });
  }

  test("account dialog closes on Escape", async ({ page }) => {
    await openApp(page, "citizen");
    await page.getByRole("button", { name: "Settings" }).click();
    await page.getByRole("button", { name: /Account and privacy/ }).click();
    const dialog = page.getByRole("dialog", { name: "Account and privacy" });
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });
});

test("the keyboard reaches the question box, with a visible ring", async ({ page }) => {
  await openApp(page, "citizen");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.getByLabel("Legal research question").focus();
  const ring = await page.locator(".composer").evaluate((node) => getComputedStyle(node).boxShadow);
  expect(ring).not.toBe("none");
});

test("reduced motion stops the animation", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await openApp(page, "citizen");
  const running = await page.evaluate(() => document.getAnimations().filter((animation) => animation.playState === "running").length);
  expect(running).toBe(0);
  await context.close();
});
