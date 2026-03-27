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

const archivedVm: VirtualMachine = {
  name: "test-vm",
  status: "archived",
  can_start: false,
  can_stop: false,
  can_archive: false,
  can_restore: true,
};

test.describe("US3 — Archive VM", () => {
  test("Archive triggers SSE progress steps then VM becomes archived", async ({ page }) => {
    await page.route("**/api/vms", (r) =>
      r.fulfill({ json: { vms: [runningVm] } })
    );

    let vmListCount = 0;
    await page.route("**/api/vms/test-vm/archive", async (route) => {
      // Update list to return archived VM after completion
      vmListCount = 0;
      await page.route("**/api/vms", (r) => {
        vmListCount++;
        r.fulfill({ json: { vms: [archivedVm] } });
      });

      const encoder = new TextEncoder();
      const body = [
        "data: " + JSON.stringify({ kind: "step", message: "Creating snapshot" }) + "\n\n",
        "data: " + JSON.stringify({ kind: "step", message: "Deleting server" }) + "\n\n",
        "data: " + JSON.stringify({ kind: "complete" }) + "\n\n",
      ].join("");

      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: encoder.encode(body),
      });
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: /archive/i }).first()).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /archive/i }).first().click();

    // Progress steps should appear
    await expect(page.getByText(/creating snapshot/i).first()).toBeVisible({ timeout: 5000 });
    // Eventually archived badge
    await expect(page.getByText("archived").first()).toBeVisible({ timeout: 10000 });
  });

  test("Archive SSE error shows ErrorBanner with completed steps", async ({ page }) => {
    await page.route("**/api/vms", (r) =>
      r.fulfill({ json: { vms: [runningVm] } })
    );

    await page.route("**/api/vms/test-vm/archive", (route) => {
      const encoder = new TextEncoder();
      const body = [
        "data: " + JSON.stringify({ kind: "step", message: "Creating snapshot" }) + "\n\n",
        "data: " + JSON.stringify({ kind: "error", message: "Snapshot failed", completedSteps: ["Creating snapshot"] }) + "\n\n",
      ].join("");

      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: encoder.encode(body),
      });
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: /archive/i }).first()).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /archive/i }).first().click();

    await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 5000 });
  });
});
