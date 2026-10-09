import { isApiError } from "../api/errors";
import type { ForeignKey, TableInfo } from "../api/queries";

export type Values = Record<string, string>;

/** `match` of a row: its primary key, or the whole row for tables without one. */
export function matchOf(table: TableInfo, row: Values): Values {
  const cols = table.primary_key.length ? table.primary_key : table.columns;
  return Object.fromEntries(cols.map((c) => [c, row[c] ?? ""]));
}

export function keyChanged(table: TableInfo, before: Values, after: Values): boolean {
  return table.primary_key.some((c) => (before[c] ?? "") !== (after[c] ?? ""));
}

/** The foreign key a column's select fills: the widest one containing it
 * (the server's lookup uses the same rule). */
export function foreignKeyOf(table: TableInfo, column: string): ForeignKey | undefined {
  return table.foreign_keys
    .filter((fk) => fk.columns.includes(column))
    .sort((a, b) => b.columns.length - a.columns.length)[0];
}

export function rowMatches(row: Values, filter: string): boolean {
  const f = filter.trim().toLowerCase();
  return !f || Object.values(row).some((v) => v.toLowerCase().includes(f));
}

export function writeError(err: unknown): unknown {
  if (isApiError(err, "stale_write")) {
    return "The table changed on the server and has been reloaded. Check the row and try again.";
  }
  return err;
}
