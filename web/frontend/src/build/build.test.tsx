import { http, HttpResponse } from "msw";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { documents, editor } from "../test/fixtures";
import { apiError, sessionAs } from "../test/handlers";
import { renderApp } from "../test/render";
import { server } from "../test/server";

type Status = Schemas["BuildStatus"];

const running: Status = {
  state: "running",
  target: "adv_tds",
  started_at: 1000,
  elapsed_s: 3,
  timed_out: false,
  log_tail: ["latexmk -pdf adv_tds.tex"],
};

beforeEach(() => {
  try {
    localStorage.clear();
  } catch {
    // ignore
  }
  server.use(sessionAs(editor));
});

describe("build panel", () => {
  it("starts a build, polls while it runs and then shows the PDF", async () => {
    let polls = 0;
    let built = false;
    server.use(
      http.get("/api/project/documents", () =>
        HttpResponse.json(
          documents.map((d) => ({ ...d, pdf_exists: d.name === "adv_tds" && built })),
        ),
      ),
      http.post("/api/build/adv_tds", () => HttpResponse.json(running, { status: 202 })),
      http.get("/api/build/latest", () => {
        polls += 1;
        if (polls < 2) return HttpResponse.json({ state: "idle" });
        built = true;
        return HttpResponse.json({
          ...running,
          state: "succeeded",
          elapsed_s: 12,
          returncode: 0,
          pdfs: ["adv_tds/adv_tds.pdf"],
        });
      }),
    );
    renderApp("/edit");
    const user = userEvent.setup();
    expect(await screen.findByText("adv_tds has not been built yet.")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Build adv_tds" }));
    expect(screen.getByRole("button", { name: "Build adv_tds" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Build delivery" })).toBeDisabled();
    expect(screen.getByLabelText("Build log")).toHaveTextContent("latexmk");
    expect(screen.getByRole("status")).toHaveTextContent("adv_tds running · 3 s");

    const frame = await screen.findByTitle("adv_tds PDF", {}, { timeout: 3000 });
    expect(frame).toHaveAttribute("src", "/api/preview/adv_tds?v=1000");
    expect(screen.getByRole("status")).toHaveTextContent("adv_tds succeeded · 12 s");
    expect(screen.getByRole("button", { name: "Build adv_tds" })).toBeEnabled();
  });

  it("reports a busy build server", async () => {
    server.use(http.post("/api/build/delivery", () => apiError(409, "build_busy", "busy")));
    renderApp("/edit");
    await userEvent.click(await screen.findByRole("button", { name: "Build delivery" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another build is running.");
  });

  it("shows errors and the log of a failed build", async () => {
    server.use(
      http.get("/api/build/latest", () =>
        HttpResponse.json({
          ...running,
          state: "failed",
          returncode: 2,
          errors: ["! Undefined control sequence."],
          log_tail: ["l.12 \\foo"],
        }),
      ),
    );
    renderApp("/edit");
    expect(await screen.findByRole("status")).toHaveTextContent("adv_tds failed");
    expect(
      within(screen.getByRole("list", { name: "Build errors" })).getByText(
        "! Undefined control sequence.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Build log")).toHaveTextContent("l.12 \\foo");
  });
});
