import { http, HttpResponse } from "msw";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { editor, fileContent } from "../test/fixtures";
import { apiError, sessionAs } from "../test/handlers";
import { renderApp } from "../test/render";
import { server } from "../test/server";

vi.mock("./MonacoEditor", () => import("../test/TextareaEditor"));

const PATH = "adv_tds/module/tls/core.tex";

beforeEach(() => {
  server.use(
    sessionAs(editor),
    http.get(`/api/project/files/${PATH}`, () =>
      HttpResponse.json(fileContent(PATH, "\\section{TLS}\n", "sha-1")),
    ),
  );
});

async function openEditor() {
  const result = renderApp(`/edit/${PATH}`);
  const source = await screen.findByLabelText(`Source of ${PATH}`);
  return { ...result, source, user: userEvent.setup() };
}

describe("document tree", () => {
  it("lists the input tree and opens files", async () => {
    const { router } = renderApp("/edit");
    const link = await screen.findByRole("link", { name: "core.tex" });
    expect(screen.getByText("missing.tex")).toHaveAttribute("title", "not found");
    await userEvent.click(link);
    expect(router.state.location.pathname).toBe(`/edit/${PATH}`);
    expect(await screen.findByLabelText(`Source of ${PATH}`)).toHaveValue("\\section{TLS}\n");
  });
});

describe("source editor", () => {
  it("saves with the read hash on Ctrl+S and shows the check results", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.put(`/api/project/files/${PATH}`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          path: PATH,
          sha256: "sha-2",
          size: 30,
          created: false,
          checks: {
            ok: false,
            checked: [PATH],
            issues: [
              {
                code: "undefined_reference",
                message: "\\sfrlink{FOO}: 'FOO' not found in sfr data",
                severity: "error",
                path: PATH,
                line: 2,
                col: 1,
              },
            ],
          },
        });
      }),
    );
    const { source, user } = await openEditor();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

    await user.type(source, "\\sfrlink{{FOO}");
    expect(screen.getByLabelText("unsaved changes")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    expect(await screen.findByText(/'FOO' not found in sfr data/)).toBeInTheDocument();
    expect(bodies).toEqual([
      { content: "\\section{TLS}\n\\sfrlink{FOO}", expected_sha256: "sha-1", create: false },
    ]);
    expect(screen.queryByLabelText("unsaved changes")).not.toBeInTheDocument();
    expect(screen.getByLabelText("markers")).toHaveTextContent("1");

    // The next save sends the new hash.
    await user.type(source, "!");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ expected_sha256: "sha-2" });
  });

  it("offers to overwrite on 409 stale_write using the current hash", async () => {
    const hashes: unknown[] = [];
    server.use(
      http.put(`/api/project/files/${PATH}`, async ({ request }) => {
        const body = (await request.json()) as { expected_sha256: string };
        hashes.push(body.expected_sha256);
        if (body.expected_sha256 !== "sha-server") {
          return apiError(409, "stale_write", "changed", { current_hash: "sha-server" });
        }
        return HttpResponse.json({ path: PATH, sha256: "sha-3", size: 1, created: false });
      }),
    );
    const { source, user } = await openEditor();
    await user.type(source, "x");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const dialog = await screen.findByRole("dialog", { name: "File changed on the server" });
    await user.click(within(dialog).getByRole("button", { name: "Overwrite with mine" }));
    await waitFor(() => expect(screen.queryByLabelText("unsaved changes")).not.toBeInTheDocument());
    expect(hashes).toEqual(["sha-1", "sha-server"]);
  });

  it("reloads the server version on 409 when asked", async () => {
    let reads = 0;
    server.use(
      http.get(`/api/project/files/${PATH}`, () => {
        reads += 1;
        const text = reads === 1 ? "old\n" : "theirs\n";
        return HttpResponse.json(fileContent(PATH, text, `sha-${reads}`));
      }),
      http.put(`/api/project/files/${PATH}`, () =>
        apiError(409, "stale_write", "changed", { current_hash: "sha-2" }),
      ),
    );
    const { source, user } = await openEditor();
    await user.type(source, "mine");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "File changed on the server" });
    await user.click(within(dialog).getByRole("button", { name: "Load server version" }));
    await waitFor(() => expect(source).toHaveValue("theirs\n"));
    expect(screen.queryByLabelText("unsaved changes")).not.toBeInTheDocument();
  });

  it("asks before leaving a file with unsaved changes", async () => {
    const { source, user, router } = await openEditor();
    await user.type(source, "x");
    await user.click(screen.getByRole("link", { name: "Common data" }));
    const dialog = await screen.findByRole("dialog", { name: "Unsaved changes" });
    await user.click(within(dialog).getByRole("button", { name: "Stay" }));
    expect(router.state.location.pathname).toBe(`/edit/${PATH}`);

    await user.click(screen.getByRole("link", { name: "Common data" }));
    await user.click(await screen.findByRole("button", { name: "Discard changes" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/data"));
  });
});
