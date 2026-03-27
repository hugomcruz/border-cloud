import { test, expect } from "@playwright/test";
import type { VirtualMachine } from "../../src/types";

const runningVm: VirtualMachine = {
  name: "test-vm",
  status: "running",
  server_id: 1,
  public_ip: "1.2.3.4",
  can_start: false,
  can_stop: true,
  can_archive: true,
  can_restore: false,
};

test.describe("US5 — IP Detection and Firewall Sync", () => {
  test("Dashboard loads without blocking UI from firewall sync", async ({ page }) => {
    await page.route("**/api/vms", (r) => r.fulfill({ json: { vms: [runningVm] } }));
    await page.route("**/api/ip", (r) => r.fulfill({ json: { ip: "10.0.0.1" } }));
    await page.route("**/api/firewall/sync", (r) =>
      r.fulfill({ json: { ip: "10.0.0.1", alreadyPresent: false } })
    );

    await page.goto("/");
    // VM card should appear — firewall sync must not block rendering
    await expect(page.getByText("test-vm").first()).toBeVisible({ timeout: 10000 });
    // No error banner
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("WarningBanner shown and dismissible when IP detection fails", async ({ page }) => {
    await page.route("**/api/vms", (r) => r.fulfill({ json: { vms: [runningVm] } }));
    await page.route("**/api/ip", (r) =>
      r.fulfill({ status: 503, json: { detail: "IP service unavailable" } })
    );

    await page.goto("/");
    // Warning should appear (non-blocking)
    const warning = page.getByRole("status").first();
    await expect(warning).toBeVisible({ timeout: 10000 });

    // Dismiss via × button
    await page.getByRole("button", { name: /dismiss|×|close/i }).first().click();
    await expect(warning).not.toBeVisible({ timeout: 3000 });
  });

  test("Second load with alreadyPresent=true shows no UI change", async ({ page }) => {
    await page.route("**/api/vms", (r) => r.fulfill({ json: { vms: [runningVm] } }));
    await page.route("**/api/ip", (r) => r.fulfill({ json: { ip: "10.0.0.1" } }));
    await page.route("**/api/firewall/sync", (r) =>
      r.fulfill({ json: { ip: "10.0.0.1", alreadyPresent: true } })
    );

    await page.goto("/");
    await expect(page.getByText("test-vm").first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.getByRole("status")).toHaveCount(0);
  });
});
