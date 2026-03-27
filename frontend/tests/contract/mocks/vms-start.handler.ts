import { http, HttpResponse } from "msw";

export const vmsStartHandler = http.post("/api/vms/:name/start", ({ params }) => {
  const { name } = params as { name: string };
  if (name === "unknown-vm") {
    return HttpResponse.json({ error: `VM '${name}' not found.` }, { status: 404 });
  }
  return HttpResponse.json({ status: "running" });
});
