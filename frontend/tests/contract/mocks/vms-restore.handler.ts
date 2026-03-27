import { http, HttpResponse } from "msw";

/**
 * SSE handler for POST /api/vms/:name/restore.
 * Emits 3-step success sequence ending with complete.
 * If name is "fail-dns", emits error after step 1 done with completedSteps.
 */
export const vmsRestoreHandler = http.post("/api/vms/:name/restore", ({ params }) => {
  const { name } = params as { name: string };

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const events =
        name === "fail-dns"
          ? [
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating server from snapshot", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating server from snapshot", status: "done" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "error", message: "DNS update failed", completedSteps: ["Creating server from snapshot"] })}\n\n`,
            ]
          : [
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating server from snapshot", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating server from snapshot", status: "done" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Updating DNS", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Updating DNS", status: "done" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Updating firewall", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Updating firewall", status: "done" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "complete", summary: `VM '${name}' restored. IP: 5.6.7.8` })}\n\n`,
            ];

      for (const event of events) {
        controller.enqueue(encoder.encode(event));
      }
      controller.close();
    },
  });

  return new HttpResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
});
