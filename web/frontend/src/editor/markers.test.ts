import { describe, expect, it } from "vitest";
import { toMarkers } from "./markers";

describe("toMarkers", () => {
  it("keeps issues of the file with a line and maps severities", () => {
    const markers = toMarkers(
      [
        { code: "a", message: "A", severity: "error", path: "x.tex", line: 3, col: 5 },
        { code: "b", message: "B", severity: "warning", path: "x.tex", line: 4 },
        { code: "c", message: "C", severity: "error", path: "y.tex", line: 1, col: 1 },
        { code: "d", message: "D", severity: "error", path: "x.tex" },
      ],
      "x.tex",
    );
    expect(markers).toHaveLength(2);
    expect(markers[0]).toMatchObject({
      severity: 8,
      startLineNumber: 3,
      startColumn: 5,
      endColumn: 6,
    });
    expect(markers[1]).toMatchObject({ severity: 4, startColumn: 1, endLineNumber: 4 });
  });
});
