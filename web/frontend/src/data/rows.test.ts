import { describe, expect, it } from "vitest";
import type { TableInfo } from "../api/queries";
import { foreignKeyOf, keyChanged, matchOf, rowMatches } from "./rows";

const table: TableInfo = {
  name: "t",
  path: "common/db/t.csv",
  columns: ["a", "b", "c"],
  primary_key: ["a"],
  foreign_keys: [
    { columns: ["b"], ref_table: "x", ref_columns: ["id"] },
    { columns: ["b", "c"], ref_table: "y", ref_columns: ["p", "q"] },
  ],
  row_count: 0,
  trailing_newline: true,
};

describe("rows", () => {
  it("matches by primary key, or the whole row without one", () => {
    expect(matchOf(table, { a: "1", b: "2", c: "3" })).toEqual({ a: "1" });
    expect(matchOf({ ...table, primary_key: [] }, { a: "1", b: "2", c: "3" })).toEqual({
      a: "1",
      b: "2",
      c: "3",
    });
  });

  it("detects key changes", () => {
    expect(keyChanged(table, { a: "1", b: "x" }, { a: "1", b: "y" })).toBe(false);
    expect(keyChanged(table, { a: "1" }, { a: "2" })).toBe(true);
  });

  it("uses the widest foreign key of a column", () => {
    expect(foreignKeyOf(table, "b")?.ref_table).toBe("y");
    expect(foreignKeyOf(table, "a")).toBeUndefined();
  });

  it("filters case-insensitively over all values", () => {
    expect(rowMatches({ a: "FCS\\_CKM.1" }, "ckm")).toBe(true);
    expect(rowMatches({ a: "x" }, "y")).toBe(false);
    expect(rowMatches({ a: "x" }, "  ")).toBe(true);
  });
});
