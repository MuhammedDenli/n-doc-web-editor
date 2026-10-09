import { Navigate, type RouteObject } from "react-router-dom";
import { LoginPage } from "./auth/LoginPage";
import { RequireAdmin, RequireAuth } from "./auth/RequireAuth";
import { DataPage } from "./data/DataPage";
import { EditorPage } from "./editor/EditorPage";
import { AppShell } from "./shell/AppShell";
import { Placeholder } from "./ui/Placeholder";

/** Opt in to React Router v7 behaviour (silences the v6 deprecation warnings). */
export const routerFuture = {
  v7_relativeSplatPath: true,
  v7_fetcherPersist: true,
  v7_normalizeFormMethod: true,
  v7_partialHydration: true,
  v7_skipActionErrorRevalidation: true,
} as const;

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/edit" replace /> },
      { path: "edit/*", element: <EditorPage /> },
      { path: "data/:table?", element: <DataPage /> },
      {
        path: "users",
        element: (
          <RequireAdmin>
            <Placeholder name="Users" />
          </RequireAdmin>
        ),
      },
      { path: "*", element: <Navigate to="/edit" replace /> },
    ],
  },
];
