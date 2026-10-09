import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { isApiError } from "../api/errors";
import { useRowWrites, type RenameResult, type RowChange, type TableInfo } from "../api/queries";
import { Dialog } from "../ui/Dialog";
import { ErrorText } from "../ui/ErrorText";
import { FkSelect } from "./FkSelect";
import { ReferencedBy } from "./ReferencedBy";
import { foreignKeyOf, keyChanged, matchOf, writeError, type Values } from "./rows";

interface Props {
  table: TableInfo;
  sha256: string;
  /** The row to edit; `null` adds a new row. */
  row: Values | null;
  onClose: () => void;
  onDone: (change: RowChange | RenameResult) => void;
}

export function RowDialog({ table, sha256, row, onClose, onDone }: Props) {
  const writes = useRowWrites(table.name);
  const [values, setValues] = useState<Values>(
    () => row ?? Object.fromEntries(table.columns.map((c) => [c, ""])),
  );
  const [renamed, setRenamed] = useState<RenameResult | null>(null);
  const editing = row !== null;
  const write = editing ? writes.update : writes.insert;
  const busy = write.isPending || writes.rename.isPending;
  const referenced = isApiError(write.error, "row_referenced") ? write.error : null;
  const canRename = editing && referenced && keyChanged(table, row, values);

  function submit(e: FormEvent) {
    e.preventDefault();
    const options = { onSuccess: onDone };
    if (editing) {
      write.mutate({ match: matchOf(table, row), values, expected_sha256: sha256 }, options);
    } else {
      writes.insert.mutate({ values, expected_sha256: sha256 }, options);
    }
  }

  function renameKey() {
    if (!row) return;
    const newKey = Object.fromEntries(table.primary_key.map((c) => [c, values[c] ?? ""]));
    writes.rename.mutate(
      { match: matchOf(table, row), new_key: newKey, expected_sha256: sha256 },
      {
        onSuccess: (result) => {
          setRenamed(result);
          onDone(result);
        },
      },
    );
  }

  const title = `${editing ? "Edit" : "Add"} ${table.name} row`;

  if (renamed) {
    return (
      <Dialog open title={title} onClose={onClose} wide>
        <p>
          Key renamed in {renamed.files.length} CSV file{renamed.files.length === 1 ? "" : "s"}.
          Other changes to this row were not saved; edit it again if needed.
        </p>
        {renamed.tex_references.length > 0 && (
          <>
            <p>Update these references in the documents:</p>
            <ul className="tex-refs">
              {renamed.tex_references.map((r, i) => (
                <li key={i}>
                  <Link to={`/edit/${r.path}`}>
                    {r.path}:{r.line}
                  </Link>{" "}
                  <code>
                    \{r.macro}
                    {"{"}
                    {r.key}
                    {"}"}
                  </code>{" "}
                  → <code>{r.replacement}</code>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="actions">
          <button className="primary" onClick={onClose}>
            Close
          </button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog open title={title} onClose={onClose} wide>
      <form onSubmit={submit} className="form row-form">
        {table.columns.map((column) => {
          const fk = foreignKeyOf(table, column);
          const isKey = table.primary_key.includes(column);
          return (
            <label key={column}>
              <span>
                {column}
                {isKey && <span className="badge">key</span>}
                {fk && <span className="badge">→ {fk.ref_table}</span>}
              </span>
              {fk ? (
                <FkSelect
                  table={table.name}
                  column={column}
                  values={values}
                  onSelect={(key) => setValues((v) => ({ ...v, ...key }))}
                />
              ) : (
                <input
                  value={values[column] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [column]: e.target.value }))}
                  spellCheck={false}
                />
              )}
            </label>
          );
        })}
        {referenced ? (
          <div className="error" role="alert">
            {referenced.message}
            <ReferencedBy details={referenced.details} />
          </div>
        ) : (
          <ErrorText error={writeError(write.error)} />
        )}
        <ErrorText error={writeError(writes.rename.error)} />
        <div className="actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          {canRename && (
            <button type="button" onClick={renameKey} disabled={busy}>
              Rename key with references
            </button>
          )}
          <button type="submit" className="primary" disabled={busy}>
            {editing ? "Save" : "Add"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
