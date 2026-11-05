import { expect, test } from "@playwright/test";
import { mockApi, openApp } from "./mock-api";

test("citizen: the tools open and say who they are", async ({ page }) => {
  await openApp(page, "citizen");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Let’s make sense of the law.");
  await page.locator(".feature-nav").getByRole("button", { name: "Know your rights" }).click();
  await expect(page.getByRole("heading", { name: "Know your rights" })).toBeVisible();
  await page.getByRole("button", { name: "Back to chat" }).click();
  await expect(page.getByLabel("Legal research question")).toBeVisible();
});

test("police: the investigation workspace lists its tools", async ({ page }) => {
  await openApp(page, "police");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("What are you investigating?");
  await page.locator(".feature-nav").getByRole("button", { name: "Investigations" }).click();
  const tools = page.getByRole("navigation", { name: "Case tools" });
  await expect(tools.getByRole("button", { name: /Deadline register/ })).toBeVisible();
  await tools.getByRole("button", { name: /Investigation record/ }).click();
  await expect(page.getByRole("tablist", { name: "Investigation record" })).toBeVisible();
});

test("advocate: the desk lists its tools", async ({ page }) => {
  await openApp(page, "advocate");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Where does your argument begin?");
  await page.locator(".feature-nav").getByRole("button", { name: "Your cases" }).click();
  await page.getByRole("navigation", { name: "Case tools" }).getByRole("button", { name: /Advocate desk/ }).click();
  await expect(page.getByRole("navigation", { name: "Advocate tools" }).getByRole("button", { name: "Calendar" })).toBeVisible();
});

test("admin: every console tab opens", async ({ page }) => {
  await openApp(page, "admin");
  await page.locator(".feature-nav").getByRole("button", { name: "Manage workspace" }).click();
  const tabs = page.getByRole("tablist", { name: "Administration sections" });
  for (const name of ["Release", "Corpus", "Quality", "Incidents", "Users", "Retention", "Models", "Audit", "Overview"]) {
    await tabs.getByRole("tab", { name }).click();
    await expect(tabs.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).not.toBeEmpty();
    await expect(page.getByRole("tabpanel").getByRole("alert")).toHaveCount(0);
  }
});

test("admin: tabs answer the arrow keys", async ({ page }) => {
  await openApp(page, "admin");
  await page.locator(".feature-nav").getByRole("button", { name: "Manage workspace" }).click();
  const tabs = page.getByRole("tablist", { name: "Administration sections" });
  await tabs.getByRole("tab", { name: "Overview" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.getByRole("tab", { name: "Release" })).toBeFocused();
  await expect(tabs.getByRole("tab", { name: "Release" })).toHaveAttribute("aria-selected", "true");
});

test("a phone brings a chosen tool into view, and nothing overflows with a case to choose", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await mockApi(page, { role: "police" });
  await page.goto("/");
  await page.getByLabel("Legal research question").waitFor();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.locator(".feature-nav").getByRole("button", { name: "Investigations" }).click();
  await page.getByRole("navigation", { name: "Case tools" }).getByRole("button", { name: /Compliance/ }).click();
  await expect(page.locator(".feature-view")).toBeInViewport();
});

test("citizens are not asked for corpus status, which the server refuses them", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/ingestion/progress")) asked.push(request.url()); });
  await openApp(page, "citizen");
  await page.waitForTimeout(500);
  expect(asked).toEqual([]);
});

test("a phone gets the navigation in a drawer that holds focus", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await mockApi(page, { role: "citizen" });
  await page.goto("/");
  const open = page.getByRole("button", { name: "Open navigation" });
  await open.click();
  await expect(page.getByRole("button", { name: "Close navigation" })).toBeFocused();
  await page.getByRole("button", { name: "Close navigation" }).click();
  await expect(open).toBeFocused();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
});
