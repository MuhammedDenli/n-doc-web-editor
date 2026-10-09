import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useLogout, type User } from "../api/queries";
import { BuildControls } from "../build/BuildControls";
import { PasswordDialog } from "./PasswordDialog";

export function TopBar({ user }: { user: User }) {
  const logout = useLogout();
  const navigate = useNavigate();
  const [passwordOpen, setPasswordOpen] = useState(false);

  return (
    <header className="topbar">
      <span className="brand">n-doc</span>
      <nav className="tabs">
        <NavLink to="/edit">Editor</NavLink>
        <NavLink to="/data">Common data</NavLink>
        {user.role === "admin" && <NavLink to="/users">Users</NavLink>}
      </nav>
      <span className="spacer" />
      <BuildControls />
      <span className="user">
        {user.username} <span className="badge">{user.role}</span>
      </span>
      <button onClick={() => setPasswordOpen(true)}>Password</button>
      <button
        onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
        disabled={logout.isPending}
      >
        Log out
      </button>
      <PasswordDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />
    </header>
  );
}
