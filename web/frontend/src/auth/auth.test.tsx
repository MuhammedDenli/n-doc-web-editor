import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { admin, editor } from "../test/fixtures";
import { apiError, noSession, sessionAs } from "../test/handlers";
import { renderApp } from "../test/render";
import { server } from "../test/server";

describe("login", () => {
  it("redirects to login without a session and back after logging in", async () => {
    server.use(
      noSession,
      http.post("/api/auth/login", async ({ request }) => {
        const body = (await request.json()) as { username: string; password: string };
        if (body.password !== "secret") return apiError(401, "invalid_credentials");
        return HttpResponse.json(admin);
      }),
    );
    const { router } = renderApp("/data");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");

    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/data"));
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Users" })).toBeInTheDocument();
  });

  it("shows the lockout wait time", async () => {
    server.use(
      noSession,
      http.post("/api/auth/login", () =>
        apiError(429, "too_many_attempts", "locked", { retry_after_s: 600 }),
      ),
    );
    renderApp("/");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "x");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 10 min");
  });

  it("logs out", async () => {
    server.use(
      sessionAs(editor),
      http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })),
    );
    const { router } = renderApp("/edit");
    await userEvent.click(await screen.findByRole("button", { name: "Log out" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });

  it("hides user admin from editors", async () => {
    server.use(sessionAs(editor));
    const { router } = renderApp("/users");
    await screen.findByText("bob");
    expect(screen.queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe("/edit"));
  });
});
