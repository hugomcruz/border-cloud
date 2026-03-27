import { http, HttpResponse } from "msw";

export const ipHandler = http.get("/api/ip", () => {
  return HttpResponse.json({ ip: "203.0.113.1" });
});

export const ipFailureHandler = http.get("/api/ip", () => {
  return HttpResponse.json(
    { detail: "Unable to detect your public IP at this time." },
    { status: 503 }
  );
});
