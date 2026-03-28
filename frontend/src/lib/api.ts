/**
 * Thin fetch wrapper for all API calls.
 * All calls use same-origin /api/* paths — Next.js rewrites them to FastAPI.
 * On 401, redirects to /login. Throws a typed error for non-OK responses.
 */

export interface ApiError {
  message: string;
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (response.status === 401) {
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { error?: string; detail?: string };
      message = body.error ?? body.detail ?? message;
    } catch {
      // ignore parse errors — use default message
    }
    const error: ApiError = { message };
    throw error;
  }

  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
