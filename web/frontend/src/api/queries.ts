import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "./client";
import { isApiError, unwrap } from "./errors";

export type User = Schemas["User"];

export const qk = {
  me: ["me"] as const,
  documents: ["documents"] as const,
  tree: (name: string) => ["tree", name] as const,
  file: (path: string) => ["file", path] as const,
  references: ["references"] as const,
};

// ---------------------------------------------------------------- auth

/** The current user; `null` without a session, `undefined` while loading. */
export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async (): Promise<User | null> => {
      try {
        return await unwrap(api.GET("/api/auth/me"));
      } catch (err) {
        if (isApiError(err) && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: Infinity,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["LoginRequest"]) => unwrap(api.POST("/api/auth/login", { body })),
    onSuccess: (user) => {
      client.clear();
      client.setQueryData(qk.me, user);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSettled: () => {
      client.clear();
      client.setQueryData(qk.me, null);
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: Schemas["PasswordChange"]) =>
      unwrap(api.POST("/api/auth/password", { body })),
  });
}

// ------------------------------------------------------------- project

export type Document = Schemas["Document"];
export type InputNode = Schemas["InputNode"];
export type FileContent = Schemas["FileContent"];
export type References = Schemas["References"];
export type CheckReport = Schemas["CheckReport"];
export type Issue = Schemas["Issue"];

export function useDocuments() {
  return useQuery({
    queryKey: qk.documents,
    queryFn: () => unwrap(api.GET("/api/project/documents")),
  });
}

export function useDocumentTree(name: string | null) {
  return useQuery({
    queryKey: qk.tree(name ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/project/documents/{name}/tree", { params: { path: { name: name! } } })),
    enabled: !!name,
  });
}

export function fetchFile(path: string) {
  return unwrap(api.GET("/api/project/files/{path}", { params: { path: { path } } }));
}

/** A file as last read; the editor keeps its own working copy. */
export function useFile(path: string) {
  return useQuery({
    queryKey: qk.file(path),
    queryFn: () => fetchFile(path),
    staleTime: Infinity,
    gcTime: 0,
  });
}

export function useSaveFile(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["FileWrite"]) =>
      unwrap(api.PUT("/api/project/files/{path}", { params: { path: { path } }, body })),
    onSuccess: () => {
      // A saved file can change the \input tree of a document.
      void client.invalidateQueries({ queryKey: ["tree"] });
    },
  });
}

export function useReferences() {
  return useQuery({
    queryKey: qk.references,
    queryFn: () => unwrap(api.GET("/api/project/references")),
    staleTime: 60_000,
  });
}
