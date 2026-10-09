import { describe, expect, it } from "vitest";
import { completionContext, completionItems } from "./completion";

const macros = { sfrlink: "sfr", tdslink: "tds", sfr: "sfr" };
const refs = {
  macros,
  keys: {
    sfr: [
      { key: "FCS_CKM.1", name: "Key generation" },
      { key: "FDP_ACC.1", name: "" },
    ],
    tds: [
      { key: "sub.tls", name: "TLS" },
      { key: "mod.tls.core", name: "Core" },
      { key: "mod.tls.io", name: "I/O" },
    ],
  },
};

describe("completionContext", () => {
  it("finds the macro whose argument is open", () => {
    expect(completionContext("see \\sfrlink{FC", macros)).toEqual({
      macro: "sfrlink",
      kind: "sfr",
      prefix: "FC",
    });
    expect(completionContext("\\tdslink{mod.tls.", macros)?.prefix).toBe("mod.tls.");
    expect(completionContext("\\sfr{", macros)?.prefix).toBe("");
  });

  it("allows an optional argument", () => {
    expect(completionContext("\\sfrlink[short]{F", macros)?.prefix).toBe("F");
  });

  it("ignores closed arguments and other macros", () => {
    expect(completionContext("\\sfrlink{FCS_CKM.1} and", macros)).toBeNull();
    expect(completionContext("\\section{Intro", macros)).toBeNull();
    expect(completionContext("\\sfrlinkx{F", macros)).toBeNull();
    expect(completionContext("plain text", macros)).toBeNull();
  });
});

describe("completionItems", () => {
  it("filters keys of the kind by prefix, case-insensitively", () => {
    const ctx = completionContext("\\tdslink{MOD.tls", macros)!;
    expect(completionItems(ctx, refs).map((i) => i.label)).toEqual(["mod.tls.core", "mod.tls.io"]);
  });

  it("carries the name as detail", () => {
    const ctx = completionContext("\\sfrlink{", macros)!;
    expect(completionItems(ctx, refs)).toEqual([
      { label: "FCS_CKM.1", detail: "Key generation" },
      { label: "FDP_ACC.1", detail: "" },
    ]);
  });

  it("returns nothing for an unknown kind", () => {
    expect(completionItems({ macro: "x", kind: "nope", prefix: "" }, refs)).toEqual([]);
  });
});
