import { http, HttpResponse } from "msw";

/** Default handlers; tests override them with `server.use(...)`. */
export const handlers = [http.get("/api/health", () => HttpResponse.json({ status: "ok" }))];

export function apiError(status: number, code: string, message = code, details = {}) {
  return HttpResponse.json({ code, message, details }, { status });
}
