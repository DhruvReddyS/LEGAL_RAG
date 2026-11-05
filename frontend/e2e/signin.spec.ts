import { expect, test } from "@playwright/test";
import { json, mockApi } from "./mock-api";

const signIn = async (page: import("@playwright/test").Page) => {
  await page.getByPlaceholder("you@example.com").fill("citizen@example.test");
  await page.getByPlaceholder("Enter your password").fill("a-test-password");
  await page.getByRole("button", { name: "Sign in" }).click();
};

test("signing in reaches the workspace", async ({ page }) => {
  await mockApi(page, { role: null, signsInAs: "citizen" });
  await page.goto("/?signin");
  await signIn(page);
  await expect(page.getByLabel("Legal research question")).toBeVisible();
});

test("a refused password shows the reason and keeps the form", async ({ page }) => {
  await mockApi(page, {
    role: null,
    overrides: { "POST /auth/cookie/login": (route) => json(route, { detail: "Incorrect email or password" }, 401) },
  });
  await page.goto("/?signin");
  await signIn(page);
  await expect(page.locator("main, .auth-shell").getByRole("alert")).toHaveText("Incorrect email or password");
  await expect(page.getByPlaceholder("you@example.com")).toHaveValue("citizen@example.test");
});

test("an unreachable server is reported, not swallowed", async ({ page }) => {
  await mockApi(page, { role: null, overrides: { "POST /auth/cookie/login": (route) => route.abort() } });
  await page.goto("/?signin");
  await signIn(page);
  await expect(page.locator("main, .auth-shell").getByRole("alert")).toContainText("Unable to reach");
});

test("the sign-in screen does not advertise figures it cannot read", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/?signin");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Checking")).toHaveCount(0);
});

test("consent is asked for before the account can be used", async ({ page }) => {
  await mockApi(page, { role: "citizen", consentRequired: true });
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "Before you continue" });
  await expect(dialog).toBeVisible();
  // There is no way out by keyboard but the two buttons it offers.
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "I accept" }).click();
  await expect(dialog).toHaveCount(0);
});
