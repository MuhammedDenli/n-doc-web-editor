import { useState, type FormEvent } from "react";
import { useMe, useUsers, useUserWrites, type User } from "../api/queries";
import { Dialog } from "../ui/Dialog";
import { ErrorText } from "../ui/ErrorText";

type Role = User["role"];

function CreateUser() {
  const { create } = useUserWrites();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("editor");

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { username, password, role },
      {
        onSuccess: () => {
          setUsername("");
          setPassword("");
          setRole("editor");
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="toolbar" aria-label="New user">
      <input
        aria-label="New username"
        placeholder="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        required
      />
      <input
        aria-label="New user password"
        placeholder="password"
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />
      <select
        aria-label="New user role"
        value={role}
        onChange={(e) => setRole(e.target.value as Role)}
      >
        <option value="editor">editor</option>
        <option value="admin">admin</option>
      </select>
      <button type="submit" className="primary" disabled={create.isPending}>
        Create user
      </button>
      <ErrorText error={create.error} />
    </form>
  );
}

function PasswordReset({ user, onClose }: { user: string; onClose: () => void }) {
  const { update } = useUserWrites();
  const [password, setPassword] = useState("");
  return (
    <Dialog open title={`New password for ${user}`} onClose={onClose}>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate({ username: user, password }, { onSuccess: onClose });
        }}
      >
        <label>
          New password
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <p className="muted">The user's sessions end.</p>
        <ErrorText error={update.error} />
        <div className="actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={update.isPending}>
            Set password
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function UsersPage() {
  const me = useMe().data;
  const users = useUsers();
  const { update, remove } = useUserWrites();
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [deleteUser, setDeleteUser] = useState<string | null>(null);

  return (
    <div className="data-page">
      <CreateUser />
      <ErrorText error={users.error ?? update.error} />
      <div className="grid-host">
        <table className="grid users">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Disabled</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {users.data?.map((u) => (
              <tr key={u.username}>
                <td>
                  {u.username}
                  {u.username === me?.username && <span className="badge">you</span>}
                </td>
                <td>
                  <select
                    aria-label={`Role of ${u.username}`}
                    value={u.role}
                    disabled={update.isPending}
                    onChange={(e) =>
                      update.mutate({ username: u.username, role: e.target.value as Role })
                    }
                  >
                    <option value="editor">editor</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Disable ${u.username}`}
                    checked={u.disabled}
                    disabled={update.isPending}
                    onChange={(e) =>
                      update.mutate({ username: u.username, disabled: e.target.checked })
                    }
                  />
                </td>
                <td className="row-actions">
                  <button onClick={() => setResetFor(u.username)}>Password</button>
                  <button className="danger" onClick={() => setDeleteUser(u.username)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {resetFor && <PasswordReset user={resetFor} onClose={() => setResetFor(null)} />}
      <Dialog
        open={deleteUser !== null}
        title="Delete user"
        onClose={() => {
          setDeleteUser(null);
          remove.reset();
        }}
      >
        <p>Delete {deleteUser}? Their sessions end.</p>
        <ErrorText error={remove.error} />
        <div className="actions">
          <button
            onClick={() => {
              setDeleteUser(null);
              remove.reset();
            }}
          >
            Cancel
          </button>
          <button
            className="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(deleteUser!, { onSuccess: () => setDeleteUser(null) })}
          >
            Delete
          </button>
        </div>
      </Dialog>
    </div>
  );
}
