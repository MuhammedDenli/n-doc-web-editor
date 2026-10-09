import { Link } from "react-router-dom";
import type { CheckReport } from "../api/queries";

interface Props {
  checks: CheckReport;
  path: string;
  onReveal: (line: number) => void;
}

/** Check results of the last save; issues in this file jump to their line. */
export function IssueList({ checks, path, onReveal }: Props) {
  if (checks.ok && checks.issues.length === 0) {
    return <p className="issues-ok ok">Checks passed.</p>;
  }
  return (
    <ul className="issues" aria-label="Check results">
      {checks.issues.map((issue, i) => {
        const where = `${issue.path ?? ""}${issue.line != null ? `:${issue.line}` : ""}`;
        return (
          <li key={i} className={issue.severity === "warning" ? "warning" : "error"}>
            <span className="badge">{issue.severity}</span>{" "}
            {issue.path === path && issue.line != null ? (
              <button className="link" onClick={() => onReveal(issue.line!)}>
                line {issue.line}
              </button>
            ) : issue.path ? (
              <Link to={`/edit/${issue.path}`}>{where}</Link>
            ) : null}{" "}
            {issue.message}
          </li>
        );
      })}
    </ul>
  );
}
