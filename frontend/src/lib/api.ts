import { getSupabase } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/**
 * Backend fetch wrapper (T-004): attaches the current Supabase session's
 * access token as a bearer header. Throws ApiError with the backend's
 * `detail` string on non-2xx so pages can show it verbatim.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  // FormData sets its own multipart Content-Type (with the boundary the
  // browser generates) - forcing application/json here would break uploads.
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const {
    data: { session },
  } = await getSupabase().auth.getSession();
  if (session) headers.set("Authorization", `Bearer ${session.access_token}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // FastAPI/pydantic 422s send a list of {loc, msg, type} instead of a
        // string - join the messages so validation errors are readable
        // inline instead of falling back to the generic status text.
        const messages = body.detail
          .map((item) => (item && typeof item === "object" && "msg" in item ? item.msg : null))
          .filter((msg): msg is string => typeof msg === "string");
        if (messages.length > 0) detail = messages.join("; ");
      }
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
