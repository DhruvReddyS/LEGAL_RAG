import { expect, test } from "@playwright/test";
import { mockApi } from "./mock-api";

test.describe("public site", () => {
  test.beforeEach(async ({ page }) => mockApi(page, { role: null }));

  test("the landing page says what it is and leads to the app", async ({ page }) => {
    await page.goto("/welcome");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Indian law");
    await expect(page.getByRole("link", { name: "Install Corpusil" }).first()).toBeVisible();
    await page.getByRole("navigation", { name: "Site" }).getByRole("link", { name: "Privacy" }).click();
    await expect(page).toHaveURL(/\/privacy/);
  });

  test("a first visit to the app opens the landing page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/welcome/);
  });

  for (const path of ["/install", "/privacy", "/terms", "/help", "/rights"]) {
    test(`${path} renders without a page error`, async ({ page }) => {
      const failures: string[] = [];
      page.on("pageerror", (error) => failures.push(error.message));
      await page.goto(path);
      await expect(page.getByRole("heading").first()).toBeVisible();
      expect(failures).toEqual([]);
    });
  }

  test("the theme chosen on the site survives a new page", async ({ page }) => {
    await page.goto("/help");
    await page.getByRole("button", { name: /Use (dark|light) theme/ }).click();
    const chosen = await page.locator("html").getAttribute("data-theme");
    await page.goto("/terms");
    await expect(page.locator("html")).toHaveAttribute("data-theme", chosen!);
  });
});

test("the rights page keeps the theme a person chose, over the system's", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.addInitScript(() => localStorage.setItem("corpusil.site-theme", "ink"));
  await page.goto("/rights");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "ink");
});
