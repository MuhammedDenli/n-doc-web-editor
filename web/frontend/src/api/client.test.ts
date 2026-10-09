import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../test/server";
import { apiError } from "../test/handlers";
import { api, setUnauthorizedHandler } from "./client";
import { ApiError, unwrap } from "./errors";

describe("api client", () => {
  it("sends the CSRF cookie as header on writes only", async () => {
    document.cookie = "ndoc_csrf=tok123; path=/";
    const seen: Record<string, string | null> = {};
    server.use(
      http.get("/api/auth/me", ({ request }) => {
        seen.get = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({ username: "a", role: "admin", disabled: false });
      }),
      http.post("/api/auth/logout", ({ request }) => {
        seen.post = request.headers.get("X-CSRF-Token");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await unwrap(api.GET("/api/auth/me"));
    await unwrap(api.POST("/api/auth/logout"));
    expect(seen).toEqual({ get: null, post: "tok123" });
  });

  it("turns error bodies into ApiError", async () => {
    server.use(
      http.get("/api/project/files/a/b%20c.tex", () =>
        apiError(409, "stale_write", "changed", { current_hash: "abc" }),
      ),
    );
    const err = await unwrap(
      api.GET("/api/project/files/{path}", { params: { path: { path: "a/b c.tex" } } }),
    ).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 409,
      code: "stale_write",
      details: { current_hash: "abc" },
    });
  });

  it("falls back to http_<status> for non-contract errors", async () => {
    server.use(http.get("/api/health", () => new HttpResponse("Bad gateway", { status: 502 })));
    const err = await unwrap(api.GET("/api/health")).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 502, code: "http_502" });
  });

  it("reports 401 outside the auth probes", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    server.use(
      http.get("/api/auth/me", () => apiError(401, "unauthenticated")),
      http.get("/api/build/latest", () => apiError(401, "unauthenticated")),
    );
    await api.GET("/api/auth/me");
    expect(handler).not.toHaveBeenCalled();
    await api.GET("/api/build/latest");
    expect(handler).toHaveBeenCalledOnce();
    setUnauthorizedHandler(null);
  });
});
