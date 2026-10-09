import type { Issue } from "../api/queries";

export interface SourceEditorProps {
  path: string;
  value: string;
  onChange: (value: string) => void;
  issues: Issue[];
  /** Scroll to and select this line; `seq` makes repeated requests distinct. */
  reveal: { line: number; seq: number } | null;
}
