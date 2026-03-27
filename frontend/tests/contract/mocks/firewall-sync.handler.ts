import { http, HttpResponse } from "msw";

let callCount = 0;

export const firewallSyncHandler = http.post("/api/firewall/sync", async ({ request }) => {
  const body = (await request.json()) as { ip?: string };

  if (!body.ip || !/^\d{1,3}(\.\d{1,3}){3}$/.test(body.ip)) {
    return HttpResponse.json({ detail: "Invalid IP address." }, { status: 400 });
  }

  callCount++;
  const alreadyPresent = callCount > 1;

  return HttpResponse.json({ ip: body.ip, alreadyPresent });
});

export const firewallSyncFailureHandler = http.post("/api/firewall/sync", () => {
  return HttpResponse.json(
    { detail: "Unable to update firewall. Please try again." },
    { status: 500 }
  );
});
