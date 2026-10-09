import { http, HttpResponse } from "msw";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { admin, editor } from "../test/fixtures";
import { apiError, sessionAs } from "../test/handlers";
import { renderApp } from "../test/render";
import { server } from "../test/server";

let users: Schemas["User"][];

beforeEach(() => {
  users = [admin, editor];
  server.use(
    sessionAs(admin),
    http.get("/api/users", () => HttpResponse.json(users)),
  );
});

describe("user admin", () => {
  it("lists users and creates one", async () => {
    let created: unknown;
    server.use(
      http.post("/api/users", async ({ request }) => {
        created = await request.json();
        const u = { ...(created as Schemas["User"]), disabled: false };
        users = [...users, u];
        return HttpResponse.json(u, { status: 201 });
      }),
    );
    renderApp("/users");
    const user = userEvent.setup();
    expect(await screen.findByRole("combobox", { name: "Role of bob" })).toHaveValue("editor");

    await user.type(screen.getByLabelText("New username"), "carol");
    await user.type(screen.getByLabelText("New user password"), "a long password");
    await user.selectOptions(screen.getByLabelText("New user role"), "admin");
    await user.click(screen.getByRole("button", { name: "Create user" }));

    expect(await screen.findByRole("combobox", { name: "Role of carol" })).toHaveValue("admin");
    expect(created).toEqual({ username: "carol", password: "a long password", role: "admin" });
  });

  it("shows the server's last-admin refusal", async () => {
    server.use(
      http.patch("/api/users/alice", () =>
        apiError(409, "last_admin", "the last active admin cannot lose the admin role"),
      ),
    );
    renderApp("/users");
    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: "Role of alice" }),
      "editor",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("last active admin");
  });

  it("deletes a user after confirmation", async () => {
    server.use(
      http.delete("/api/users/bob", () => {
        users = users.filter((u) => u.username !== "bob");
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/users");
    const user = userEvent.setup();
    const row = (await screen.findByRole("combobox", { name: "Role of bob" })).closest("tr")!;
    await user.click(within(row).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete user" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(screen.queryByRole("combobox", { name: "Role of bob" })).not.toBeInTheDocument(),
    );
  });

  it("is not reachable for editors", async () => {
    server.use(sessionAs(editor));
    const { router } = renderApp("/users");
    await screen.findByText("bob");
    await waitFor(() => expect(router.state.location.pathname).toBe("/edit"));
  });
});
