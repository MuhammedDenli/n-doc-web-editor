import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const CSRF_COOKIE = "ndoc_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

export function readCookie(name: string): string | null {
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

let unauthorizedHandler: (() => void) | null = null;

/** Called when a request other than login/me returns 401 (session expired). */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const AUTH_PROBES = ["/api/auth/login", "/api/auth/me"];

export const sessionMiddleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method)) {
      const token = readCookie(CSRF_COOKIE);
      if (token) request.headers.set(CSRF_HEADER, token);
    }
    return request;
  },
  onResponse({ request, response }) {
    if (response.status === 401) {
      const path = new URL(request.url).pathname;
      if (!AUTH_PROBES.includes(path)) unauthorizedHandler?.();
    }
    return response;
  },
};

/** Path parameters are encoded per segment: repo paths (`{path}`) keep their `/`
 * so `GET /api/project/files/adv_tds/adv_tds.tex` matches the contract. */
export function serializePath(pathname: string, params: Record<string, unknown>): string {
  return pathname.replace(/\{(\w+)\}/g, (_, name: string) =>
    String(params[name] ?? "")
      .split("/")
      .map(encodeURIComponent)
      .join("/"),
  );
}

export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  pathSerializer: serializePath,
  // Resolve fetch per call so test interceptors (MSW) installed later still apply.
  fetch: (request) => globalThis.fetch(request),
});
api.use(sessionMiddleware);
