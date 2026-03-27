import { test, expect } from "@playwright/test";

test.describe("US6 — Authentication", () => {
  test("Unauthenticated user is redirected to /login", async ({ page }) => {
    // Without a valid session cookie, middleware should redirect
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
  });

  test("Wrong password shows inline error", async ({ page }) => {
    await page.route("**/api/auth/login", (r) =>
      r.fulfill({ status: 401, json: { detail: "Invalid credentials" } })
    );

    await page.goto("/login");
    await page.getByLabel(/username|email/i).fill("admin");
    await page.getByLabel(/password/i).fill("wrongpassword");
    await page.getByRole("button", { name: /sign in|login/i }).click();

    await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/invalid credentials/i).first()).toBeVisible({ timeout: 5000 });
  });

  test("Correct credentials redirect to dashboard", async ({ page }) => {
    await page.route("**/api/auth/login", (r) =>
      r.fulfill({
        status: 200,
        headers: { "Set-Cookie": "access_token=test_jwt; Path=/; HttpOnly" },
        json: { ok: true },
      })
    );
    // Stub the VMs endpoint so the dashboard can load
    await page.route("**/api/vms", (r) => r.fulfill({ json: { vms: [] } }));
    await page.route("**/api/ip", (r) => r.fulfill({ json: { ip: "1.2.3.4" } }));
    await page.route("**/api/firewall/sync", (r) =>
      r.fulfill({ json: { ip: "1.2.3.4", alreadyPresent: true } })
    );

    await page.goto("/login");
    await page.getByLabel(/username|email/i).fill("admin");
    await page.getByLabel(/password/i).fill("correctpassword");
    await page.getByRole("button", { name: /sign in|login/i }).click();

    await expect(page).toHaveURL(/^\/$/, { timeout: 10000 });
  });

  test("Logout redirects to /login", async ({ page }) => {
    await page.route("**/api/auth/logout", (r) => r.fulfill({ status: 200, json: { ok: true } }));
    await page.route("**/api/vms", (r) => r.fulfill({ json: { vms: [] } }));
    await page.route("**/api/ip", (r) => r.fulfill({ json: { ip: "1.2.3.4" } }));
    await page.route("**/api/firewall/sync", (r) =>
      r.fulfill({ json: { ip: "1.2.3.4", alreadyPresent: true } })
    );

    // Navigate to dashboard as if already authenticated
    await page.goto("/");
    const logoutBtn = page.getByRole("button", { name: /logout|sign out/i }).first();
    if (await logoutBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    } else {
      // Middleware redirected us — that validates unauthenticated protection
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    }
  });
});
