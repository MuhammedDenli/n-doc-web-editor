import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useTable,
  useTables,
  type CheckReport,
  type RenameResult,
  type RowChange,
  type TableInfo,
} from "../api/queries";
import { ErrorText } from "../ui/ErrorText";
import { DeleteDialog } from "./DeleteDialog";
import { RowDialog } from "./RowDialog";
import { rowMatches, type Values } from "./rows";

type Edit = { kind: "add" } | { kind: "edit"; row: Values } | { kind: "delete"; row: Values };

export function DataPage() {
  const { table: name } = useParams();
  const navigate = useNavigate();
  const tables = useTables();
  const info = tables.data?.find((t) => t.name === name);

  return (
    <div className="data-page">
      <div className="toolbar">
        <label className="inline">
          Table
          <select value={name ?? ""} onChange={(e) => navigate(`/data/${e.target.value}`)}>
            <option value="" disabled>
              choose…
            </option>
            {tables.data?.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name} ({t.row_count})
              </option>
            ))}
          </select>
        </label>
      </div>
      <ErrorText error={tables.error} />
      {name && tables.data && !info && <p className="error">Unknown table {name}.</p>}
      {info && <TableView key={info.name} info={info} />}
    </div>
  );
}

function TableView({ info }: { info: TableInfo }) {
  const table = useTable(info.name);
  const [filter, setFilter] = useState("");
  const [edit, setEdit] = useState<Edit | null>(null);
  const [checks, setChecks] = useState<CheckReport | null>(null);
  const rows = useMemo(
    () => (table.data?.rows ?? []).filter((r) => rowMatches(r.values, filter)),
    [table.data, filter],
  );

  function done(change: RowChange | RenameResult) {
    setChecks(change.checks);
    if (!("tex_references" in change)) setEdit(null);
  }

  return (
    <>
      <div className="toolbar">
        <input
          type="search"
          placeholder="Filter rows"
          aria-label="Filter rows"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <span className="muted">
          {info.path} · key: {info.primary_key.join(", ") || "whole row"}
        </span>
        <span className="spacer" />
        <button className="primary" onClick={() => setEdit({ kind: "add" })} disabled={!table.data}>
          Add row
        </button>
      </div>
      {checks && !checks.ok && (
        <div className="banner error" role="status">
          Data checks after the last change:
          <ul>
            {checks.issues.map((i, n) => (
              <li key={n}>{i.message}</li>
            ))}
          </ul>
        </div>
      )}
      <ErrorText error={table.error} />
      {table.data && (
        <div className="grid-host">
          <table className="grid">
            <thead>
              <tr>
                {table.data.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.line}>
                  {table.data.columns.map((c) => (
                    <td key={c}>{r.values[c]}</td>
                  ))}
                  <td className="row-actions">
                    <button onClick={() => setEdit({ kind: "edit", row: r.values })}>Edit</button>
                    <button
                      className="danger"
                      onClick={() => setEdit({ kind: "delete", row: r.values })}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {table.data.truncated && (
            <p className="muted pad">
              Showing {table.data.rows.length} of {table.data.total} rows.
            </p>
          )}
        </div>
      )}
      {table.data && edit?.kind === "delete" && (
        <DeleteDialog
          table={info}
          sha256={table.data.sha256}
          row={edit.row}
          onClose={() => setEdit(null)}
          onDone={done}
        />
      )}
      {table.data && (edit?.kind === "add" || edit?.kind === "edit") && (
        <RowDialog
          table={info}
          sha256={table.data.sha256}
          row={edit.kind === "edit" ? edit.row : null}
          onClose={() => setEdit(null)}
          onDone={done}
        />
      )}
    </>
  );
}
