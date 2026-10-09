import type { Issue } from "../api/queries";

// monaco.MarkerSeverity values (kept here so this module stays Monaco-free).
const SEVERITY = { error: 8, warning: 4 } as const;

export interface Marker {
  severity: number;
  message: string;
  source: string;
  code: string;
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
}

/** Check issues of one file as Monaco markers (core lines/columns are 1-based). */
export function toMarkers(issues: Issue[], path: string): Marker[] {
  return issues
    .filter((i) => i.path === path && i.line != null)
    .map((i) => {
      const line = i.line!;
      const col = i.col ?? 1;
      return {
        severity: SEVERITY[i.severity],
        message: i.message,
        source: "ndoc",
        code: i.code,
        startLineNumber: line,
        startColumn: col,
        endLineNumber: line,
        // Without a column the whole line is marked.
        endColumn: i.col != null ? col + 1 : Number.MAX_SAFE_INTEGER,
      };
    });
}
