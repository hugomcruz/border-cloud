import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * SSE proxy for GET /vms/operations/:op_id/stream.
 * Next.js rewrites buffer streaming responses, so this route handler
 * pipes the upstream SSE body directly to the browser without buffering.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { op_id: string } },
): Promise<Response> {
  const cookie = request.headers.get("cookie") ?? "";
  const upstream = await fetch(
    `${API_URL}/vms/operations/${encodeURIComponent(params.op_id)}/stream`,
    { headers: { cookie } },
  );

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    return new Response(text, { status: upstream.status });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
