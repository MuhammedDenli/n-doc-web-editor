import { isApiError } from "../api/errors";
import { useRowWrites, type RowChange, type TableInfo } from "../api/queries";
import { Dialog } from "../ui/Dialog";
import { ErrorText } from "../ui/ErrorText";
import { ReferencedBy } from "./ReferencedBy";
import { matchOf, writeError, type Values } from "./rows";

interface Props {
  table: TableInfo;
  sha256: string;
  row: Values;
  onClose: () => void;
  onDone: (change: RowChange) => void;
}

export function DeleteDialog({ table, sha256, row, onClose, onDone }: Props) {
  const { remove } = useRowWrites(table.name);
  const match = matchOf(table, row);
  const referenced = isApiError(remove.error, "row_referenced") ? remove.error : null;

  return (
    <Dialog open title={`Delete ${table.name} row`} onClose={onClose}>
      <p>
        Delete{" "}
        <code>
          {Object.entries(match)
            .map(([c, v]) => `${c}=${v}`)
            .join(", ")}
        </code>
        ?
      </p>
      {referenced ? (
        <div className="error" role="alert">
          {referenced.message}
          <ReferencedBy details={referenced.details} />
        </div>
      ) : (
        <ErrorText error={writeError(remove.error)} />
      )}
      <div className="actions">
        <button onClick={onClose}>{referenced ? "Close" : "Cancel"}</button>
        {!referenced && (
          <button
            className="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate({ match, expected_sha256: sha256 }, { onSuccess: onDone })}
          >
            Delete
          </button>
        )}
      </div>
    </Dialog>
  );
}
