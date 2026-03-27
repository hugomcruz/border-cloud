import { test, expect } from "@playwright/test";
import type { VirtualMachine } from "../../src/types";

const archivedVm: VirtualMachine = {
  name: "test-vm",
  status: "archived",
  snapshot_id: 999,
  can_start: false,
  can_stop: false,
  can_archive: false,
  can_restore: true,
};

const restoredVm: VirtualMachine = {
  name: "test-vm",
  status: "running",
  server_id: 2,
  public_ip: "5.6.7.8",
  can_start: false,
  can_stop: true,
  can_archive: true,
  can_restore: false,
};

const sseBody = (events: object[]) => {
  const encoder = new TextEncoder();
  return encoder.encode(events.map((e) => "data: " + JSON.stringify(e) + "\n\n").join(""));
};

test.describe("US4 — Restore VM", () => {
  test("Restore triggers 3 SSE progress steps then VM shows running with new IP", async ({ page }) => {
    await page.route("**/api/vms", (r) =>
      r.fulfill({ json: { vms: [archivedVm] } })
    );

    await page.route("**/api/vms/test-vm/restore", async (route) => {
      await page.route("**/api/vms", (r) => r.fulfill({ json: { vms: [restoredVm] } }));

      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody([
          { kind: "step", message: "Creating server from snapshot" },
          { kind: "step", message: "Updating DNS record" },
          { kind: "step", message: "Updating firewall rules" },
          { kind: "complete" },
        ]),
      });
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: /restore/i }).first()).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /restore/i }).first().click();

    await expect(page.getByText(/creating server/i).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("running").first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("5.6.7.8").first()).toBeVisible({ timeout: 5000 });
  });

  test("DNS failure shows ErrorBanner with completed steps", async ({ page }) => {
    await page.route("**/api/vms", (r) =>
      r.fulfill({ json: { vms: [archivedVm] } })
    );

    await page.route("**/api/vms/test-vm/restore", (route) => {
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody([
          { kind: "step", message: "Creating server from snapshot" },
          {
            kind: "error",
            message: "DNS update failed",
            completedSteps: ["Creating server from snapshot"],
          },
        ]),
      });
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: /restore/i }).first()).toBeVisible({ timeout: 10000 });
    await page.getByRole("button", { name: /restore/i }).first().click();

    await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/dns update failed/i).first()).toBeVisible({ timeout: 5000 });
  });
});
