import type { References } from "../api/queries";

export interface CompletionContext {
  macro: string;
  kind: string;
  /** Text typed inside the braces so far (may contain dots: `mod.tls.`). */
  prefix: string;
}

const OPEN_ARGUMENT = /\\([A-Za-z@]+)\*?(?:\[[^\]]*\])?\{([^{}]*)$/;

/** The reference macro whose argument the cursor is in, from the line up to the cursor. */
export function completionContext(
  lineUntilCursor: string,
  macros: Record<string, string>,
): CompletionContext | null {
  const m = OPEN_ARGUMENT.exec(lineUntilCursor);
  if (!m) return null;
  const macro = m[1]!;
  const kind = macros[macro];
  if (!kind) return null;
  return { macro, kind, prefix: m[2]! };
}

export interface CompletionItem {
  label: string;
  detail: string;
}

/** Valid keys for the context, matching the typed prefix case-insensitively
 * (n-doc lookups are COLLATE NOCASE). */
export function completionItems(ctx: CompletionContext, refs: References): CompletionItem[] {
  const prefix = ctx.prefix.toLowerCase();
  return (refs.keys[ctx.kind] ?? [])
    .filter((k) => k.key.toLowerCase().startsWith(prefix))
    .map((k) => ({ label: k.key, detail: k.name ?? "" }));
}
