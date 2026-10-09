import { Link } from "react-router-dom";

interface Reference {
  table?: string;
  line?: number;
  columns?: string[];
  values?: string[];
}

/** `details.referenced_by` of a 409 row_referenced: the rows that still use the key. */
export function ReferencedBy({ details }: { details: Record<string, unknown> }) {
  const refs = (details.referenced_by as Reference[] | undefined) ?? [];
  const count = typeof details.count === "number" ? details.count : refs.length;
  if (!refs.length) return null;
  return (
    <div className="referenced-by">
      <p>
        Still referenced by {count} row{count === 1 ? "" : "s"}:
      </p>
      <ul>
        {refs.map((r, i) => (
          <li key={i}>
            <Link to={`/data/${r.table}`}>{r.table}</Link> line {r.line}:{" "}
            <code>{(r.columns ?? []).map((c, j) => `${c}=${r.values?.[j] ?? ""}`).join(", ")}</code>
          </li>
        ))}
      </ul>
      {count > refs.length && <p className="muted">… and {count - refs.length} more.</p>}
    </div>
  );
}
