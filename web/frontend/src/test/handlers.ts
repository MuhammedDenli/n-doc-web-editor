import { http, HttpResponse } from "msw";
import type { Schemas } from "../api/client";

/** Default handlers; tests override them with `server.use(...)`. */
export const handlers = [http.get("/api/health", () => HttpResponse.json({ status: "ok" }))];

export function apiError(status: number, code: string, message = code, details = {}) {
  return HttpResponse.json({ code, message, details }, { status });
}

/** A logged-in session for `user`. */
export function sessionAs(user: Schemas["User"]) {
  return http.get("/api/auth/me", () => HttpResponse.json(user));
}

export const noSession = http.get("/api/auth/me", () => apiError(401, "unauthenticated"));
