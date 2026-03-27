import { http, HttpResponse } from "msw";

/**
 * SSE handler for POST /api/vms/:name/archive.
 * Emits 5 events: step in-progress, step done, step in-progress, step done, complete.
 * If name is "fail-vm", emits an error after the first step.
 */
export const vmsArchiveHandler = http.post("/api/vms/:name/archive", ({ params }) => {
  const { name } = params as { name: string };

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const events =
        name === "fail-vm"
          ? [
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating snapshot", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "error", message: "Snapshot failed", completedSteps: [] })}\n\n`,
            ]
          : [
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating snapshot", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Creating snapshot", status: "done" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Deleting server", status: "in-progress" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "step", step: { step: "Deleting server", status: "done" } })}\n\n`,
              `data: ${JSON.stringify({ kind: "complete", summary: `VM '${name}' archived successfully.` })}\n\n`,
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
