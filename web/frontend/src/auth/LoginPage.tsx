import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate, type Location } from "react-router-dom";
import { isApiError } from "../api/errors";
import { useLogin, useMe } from "../api/queries";
import { ErrorText } from "../ui/ErrorText";

function loginErrorText(err: unknown): unknown {
  if (isApiError(err, "invalid_credentials")) return "Invalid username or password.";
  if (isApiError(err, "too_many_attempts")) {
    const wait = Number(err.details.retry_after_s ?? 0);
    return `Too many failed logins. Try again in ${Math.ceil(wait / 60)} min.`;
  }
  return err;
}

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: Location } | null)?.from;
  const target = from ? `${from.pathname}${from.search}` : "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (me.data) return <Navigate to={target} replace />;

  function submit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ username, password }, { onSuccess: () => navigate(target, { replace: true }) });
  }

  return (
    <main className="login">
      <form onSubmit={submit} className="card">
        <h1>n-doc editor</h1>
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <ErrorText error={login.error && loginErrorText(login.error)} />
        <button type="submit" className="primary" disabled={login.isPending}>
          Log in
        </button>
      </form>
    </main>
  );
}
