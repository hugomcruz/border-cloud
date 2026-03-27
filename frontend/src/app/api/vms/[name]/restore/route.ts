import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

/**
 * Start a restore operation on the backend.
 * Returns { op_id } with status 202 — the client should then
 * open GET /api/vms/operations/[op_id]/stream to receive SSE progress.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { name: string } },
): Promise<Response> {
  const cookie = request.headers.get("cookie") ?? "";
  const upstream = await fetch(
    `${API_URL}/vms/${encodeURIComponent(params.name)}/restore`,
    { method: "POST", headers: { cookie } },
  );
  const data = await upstream.json();
  return Response.json(data, { status: upstream.status });
}
