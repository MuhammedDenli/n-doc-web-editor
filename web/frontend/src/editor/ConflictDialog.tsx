import { Dialog } from "../ui/Dialog";

interface Props {
  open: boolean;
  busy: boolean;
  onReload: () => void;
  onOverwrite: () => void;
  onCancel: () => void;
}

/** 409 stale_write: the file changed on the server since it was opened. */
export function ConflictDialog({ open, busy, onReload, onOverwrite, onCancel }: Props) {
  return (
    <Dialog open={open} title="File changed on the server" onClose={onCancel}>
      <p>
        Someone else (or the agent) saved this file after you opened it. Load their version and drop
        your changes, or overwrite it with yours.
      </p>
      <div className="actions">
        <button onClick={onCancel}>Cancel</button>
        <button onClick={onReload} disabled={busy}>
          Load server version
        </button>
        <button className="primary" onClick={onOverwrite} disabled={busy}>
          Overwrite with mine
        </button>
      </div>
    </Dialog>
  );
}
