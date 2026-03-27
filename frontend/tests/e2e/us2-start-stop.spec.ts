import { test, expect } from "@playwright/test";
import type { VirtualMachine } from "../../src/types";

const stoppedVm: VirtualMachine = {
  name: "test-vm",
  status: "stopped",
  server_id: 1,
  can_start: true,
  can_stop: false,
  can_archive: true,
  can_restore: false,
};

const runningVm: VirtualMachine = {
  ...stoppedVm,
  status: "running",
  public_ip: "1.2.3.4",
  can_start: false,
  can_stop: true,
};

test.describe("US2 — Start and Stop VM", () => {
  test("Start button triggers status change to running", async ({ page }) => {
    // Mock GET /api/vms with stopped VM
    await page.route("**/api/vms", (route) =>
      route.fulfill({ json: { vms: [stoppedVm] } })
    );
    await page.route("**/api/vms/test-vm/start", async (route) => {
      // After start, the VM list will return running
      await page.route("**/api/vms", (r) =>
        r.fulfill({ json: { vms: [runningVm] } })
      );
      route.fulfill({ json: { status: "running" } });
    });

    await page.goto("/");
    const startBtn = page.getByRole("button", { name: /start/i }).first();
    await expect(startBtn).toBeVisible({ timeout: 10000 });
    await startBtn.click();

    // After response, running badge should appear
    await expect(page.getByText("running").first()).toBeVisible({ timeout: 5000 });
  });

  test("Stop button triggers status change to stopped", async ({ page }) => {
    await page.route("**/api/vms", (route) =>
      route.fulfill({ json: { vms: [runningVm] } })
    );
    await page.route("**/api/vms/test-vm/stop", async (route) => {
      await page.route("**/api/vms", (r) =>
        r.fulfill({ json: { vms: [stoppedVm] } })
      );
      route.fulfill({ json: { status: "stopped" } });
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: /stop/i }).first()).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /stop/i }).first().click();

    await expect(page.getByText("stopped").first()).toBeVisible({ timeout: 5000 });
  });

  test("ErrorBanner appears on 404 response", async ({ page }) => {
    await page.route("**/api/vms", (route) =>
      route.fulfill({ json: { vms: [stoppedVm] } })
    );
    await page.route("**/api/vms/test-vm/start", (route) =>
      route.fulfill({ status: 404, json: { detail: "VM not found" } })
    );

    await page.goto("/");
    await expect(page.getByRole("button", { name: /start/i }).first()).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /start/i }).first().click();

    await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 5000 });
  });
});
