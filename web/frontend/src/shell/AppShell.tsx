import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { setUnauthorizedHandler } from "../api/client";
import { qk, useMe } from "../api/queries";
import { TopBar } from "./TopBar";

export function AppShell() {
  const user = useMe().data!;
  const client = useQueryClient();
  const navigate = useNavigate();

  // An expired session on any call sends the user back to the login page.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      client.setQueryData(qk.me, null);
      navigate("/login");
    });
    return () => setUnauthorizedHandler(null);
  }, [client, navigate]);

  return (
    <div className="shell">
      <TopBar user={user} />
      <aside className="sidebar" />
      <main className="content">
        <Outlet />
      </main>
      <aside className="panel" />
    </div>
  );
}
