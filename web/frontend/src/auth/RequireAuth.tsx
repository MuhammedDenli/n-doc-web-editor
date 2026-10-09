import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useMe } from "../api/queries";
import { ErrorText } from "../ui/ErrorText";

export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <p className="muted pad">Loading…</p>;
  if (me.isError) return <ErrorText error={me.error} />;
  if (!me.data) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const me = useMe();
  if (me.data?.role !== "admin") return <Navigate to="/" replace />;
  return children;
}
