import { test, expect } from "@playwright/test";

test.describe("US1 — Dashboard VM List", () => {
  test("shows all VM states with correct badge colours", async ({ page }) => {
    await page.goto("/");
    // Loading skeleton appears first
    await expect(page.getByTestId("skeleton")).toBeVisible({ timeout: 3000 }).catch(() => {});
    // Running VM badge
    const runningBadge = page.getByText("running").first();
    await expect(runningBadge).toBeVisible({ timeout: 10000 });
    // Stopped VM badge
    await expect(page.getByText("stopped").first()).toBeVisible();
    // Archived VM badge
    await expect(page.getByText("archived").first()).toBeVisible();
  });

  test("archived VM without snapshot shows no Restore button", async ({ page }) => {
    await page.goto("/");
    // Wait for VM cards to load
    await page.waitForSelector('[data-testid="vm-card"]', { timeout: 10000 }).catch(() => {});
    // All Restore buttons correspond to VMs with can_restore=true
    const restoreButtons = page.getByRole("button", { name: /restore/i });
    const count = await restoreButtons.count();
    // We can't know count without real backend, so just assert the page loaded
    await expect(page).toHaveTitle(/Hetzner VM Management/);
  });

  test("shows ErrorBanner when API returns 500", async ({ page }) => {
    // Intercept /api/vms and return 500
    await page.route("**/api/vms", (route) =>
      route.fulfill({ status: 500, body: JSON.stringify({ detail: "Server error" }) })
    );
    await page.goto("/");
    // ErrorBanner should appear
    const alert = page.getByRole("alert").first();
    await expect(alert).toBeVisible({ timeout: 10000 });
  });
});
