import { useState, type FormEvent } from "react";
import { isApiError } from "../api/errors";
import { useChangePassword } from "../api/queries";
import { Dialog } from "../ui/Dialog";
import { ErrorText } from "../ui/ErrorText";

export function PasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  function close() {
    setCurrent("");
    setNext("");
    change.reset();
    onClose();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    change.mutate({ current_password: current, new_password: next }, { onSuccess: close });
  }

  const error = isApiError(change.error, "invalid_credentials")
    ? "The current password is wrong."
    : change.error;

  return (
    <Dialog open={open} title="Change password" onClose={close}>
      <form onSubmit={submit} className="form">
        <label>
          Current password
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label>
          New password
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        <ErrorText error={error} />
        <div className="actions">
          <button type="button" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={change.isPending}>
            Change
          </button>
        </div>
      </form>
    </Dialog>
  );
}
