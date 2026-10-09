import { http, HttpResponse } from "msw";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { editor } from "../test/fixtures";
import { apiError, sessionAs } from "../test/handlers";
import { renderApp } from "../test/render";
import { server } from "../test/server";

const okChecks = { ok: true, issues: [], checked: [] };

const tables: Schemas["TableInfo"][] = [
  {
    name: "sfr",
    path: "common/db/sfr.csv",
    columns: ["label", "name"],
    primary_key: ["label"],
    foreign_keys: [],
    row_count: 1,
    trailing_newline: true,
  },
  {
    name: "interfaces",
    path: "common/db/interfaces.csv",
    columns: ["subsystem", "module", "label"],
    primary_key: ["subsystem", "module", "label"],
    foreign_keys: [
      {
        columns: ["subsystem", "module"],
        ref_table: "modules",
        ref_columns: ["subsystem", "label"],
      },
    ],
    row_count: 0,
    trailing_newline: true,
  },
];

function tableData(table: string, rows: Record<string, string>[]): Schemas["TableData"] {
  const info = tables.find((t) => t.name === table)!;
  return {
    table,
    path: info.path,
    columns: info.columns,
    primary_key: info.primary_key,
    sha256: `sha-${table}`,
    rows: rows.map((values, i) => ({ line: i + 2, values })),
    total: rows.length,
    truncated: false,
  };
}

beforeEach(() => {
  server.use(
    sessionAs(editor),
    http.get("/api/data/tables", () => HttpResponse.json(tables)),
    http.get("/api/data/sfr", () =>
      HttpResponse.json(tableData("sfr", [{ label: "FCS\\_CKM.1", name: "Key generation" }])),
    ),
    http.get("/api/data/interfaces", () => HttpResponse.json(tableData("interfaces", []))),
  );
});

describe("common data", () => {
  it("shows why a referenced row cannot be deleted", async () => {
    let body: unknown;
    server.use(
      http.delete("/api/data/sfr", async ({ request }) => {
        body = await request.json();
        return apiError(409, "row_referenced", "the key is still referenced by other rows", {
          referenced_by: [
            {
              table: "sfr_obj",
              path: "common/db/sfr_obj.csv",
              line: 7,
              columns: ["sfr"],
              values: ["FCS\\_CKM.1"],
            },
          ],
          count: 3,
        });
      }),
    );
    renderApp("/data/sfr");
    const user = userEvent.setup();
    // LaTeX escapes are shown as stored.
    expect(await screen.findByText("FCS\\_CKM.1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete sfr row" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("still referenced");
    expect(alert).toHaveTextContent("Still referenced by 3 rows");
    expect(alert).toHaveTextContent("sfr_obj line 7: sfr=FCS\\_CKM.1");
    expect(alert).toHaveTextContent("and 2 more");
    expect(body).toEqual({ match: { label: "FCS\\_CKM.1" }, expected_sha256: "sha-sfr" });
  });

  it("fills every column of a composite foreign key from one choice", async () => {
    let inserted: unknown;
    server.use(
      http.get("/api/data/interfaces/lookup", ({ request }) => {
        const column = new URL(request.url).searchParams.get("column");
        const options = [
          { value: "core", name: "Core", key: { subsystem: "tls", module: "core" } },
          { value: "core", name: "Core (SSH)", key: { subsystem: "ssh", module: "core" } },
        ];
        return HttpResponse.json(
          options.map((o) => ({ ...o, value: column === "subsystem" ? o.key.subsystem : o.value })),
        );
      }),
      http.post("/api/data/interfaces", async ({ request }) => {
        inserted = await request.json();
        return HttpResponse.json(
          {
            table: "interfaces",
            path: "common/db/interfaces.csv",
            sha256: "sha-2",
            line: 2,
            row: {},
            checks: okChecks,
          },
          { status: 201 },
        );
      }),
    );
    renderApp("/data/interfaces");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add row" }));
    const dialog = await screen.findByRole("dialog", { name: "Add interfaces row" });

    const module = within(dialog).getByRole("combobox", { name: "module" });
    await waitFor(() => expect(module).toBeEnabled());
    await user.selectOptions(module, "ssh / core — Core (SSH)");
    // The other column of the key follows.
    expect(within(dialog).getByRole("combobox", { name: "subsystem" })).toHaveDisplayValue(
      "ssh / core — Core (SSH)",
    );
    await user.type(within(dialog).getByRole("textbox"), "if1");
    await user.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(inserted).toEqual({
      values: { subsystem: "ssh", module: "core", label: "if1" },
      expected_sha256: "sha-interfaces",
    });
  });

  it("offers rename-key when a referenced key is changed", async () => {
    let renameBody: unknown;
    server.use(
      http.put("/api/data/sfr", () =>
        apiError(409, "row_referenced", "the key is still referenced by other rows", {
          referenced_by: [],
        }),
      ),
      http.post("/api/data/sfr/rename-key", async ({ request }) => {
        renameBody = await request.json();
        return HttpResponse.json({
          table: "sfr",
          old_key: { label: "FCS\\_CKM.1" },
          new_key: { label: "FCS\\_CKM.2" },
          files: [{ path: "common/db/sfr.csv", sha256: "x", rows_changed: 1 }],
          tex_references: [
            {
              path: "ase/sfr.tex",
              line: 4,
              col: 1,
              macro: "sfrlink",
              key: "FCS\\_CKM.1",
              replacement: "\\sfrlink{FCS\\_CKM.2}",
            },
          ],
          checks: okChecks,
        });
      }),
    );
    renderApp("/data/sfr");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit sfr row" });
    const label = within(dialog).getAllByRole("textbox")[0]!;
    await user.clear(label);
    await user.type(label, "FCS\\_CKM.2");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await user.click(
      await within(dialog).findByRole("button", { name: "Rename key with references" }),
    );
    expect(await within(dialog).findByRole("link", { name: "ase/sfr.tex:4" })).toHaveAttribute(
      "href",
      "/edit/ase/sfr.tex",
    );
    expect(renameBody).toEqual({
      match: { label: "FCS\\_CKM.1" },
      new_key: { label: "FCS\\_CKM.2" },
      expected_sha256: "sha-sfr",
    });
  });
});
