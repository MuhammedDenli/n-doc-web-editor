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
  tables: ["tables"] as const,
  table: (name: string) => ["table", name] as const,
  lookup: (table: string, column: string) => ["lookup", table, column] as const,
  buildTargets: ["buildTargets"] as const,
  build: ["build"] as const,
  users: ["users"] as const,
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

// ---------------------------------------------------------------- data

export type TableInfo = Schemas["TableInfo"];
export type TableData = Schemas["TableData"];
export type ForeignKey = Schemas["ForeignKey"];
export type LookupOption = Schemas["LookupOption"];
export type RowChange = Schemas["RowChange"];
export type RenameResult = Schemas["RenameResult"];

export function useTables() {
  return useQuery({ queryKey: qk.tables, queryFn: () => unwrap(api.GET("/api/data/tables")) });
}

export function useTable(table: string | undefined) {
  return useQuery({
    queryKey: qk.table(table ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/data/{table}", { params: { path: { table: table! }, query: {} } })),
    enabled: !!table,
  });
}

/** Allowed values of `table.column` (for FK columns: the referenced rows). */
export function useLookup(table: string, column: string) {
  return useQuery({
    queryKey: qk.lookup(table, column),
    queryFn: () =>
      unwrap(
        api.GET("/api/data/{table}/lookup", {
          params: { path: { table }, query: { column, limit: 1000 } },
        }),
      ),
  });
}

/** Row writes; afterwards every table view, FK option and completion key is stale. */
export function useRowWrites(table: string) {
  const client = useQueryClient();
  const onSuccess = () => {
    for (const key of [["table"], ["tables"], ["lookup"], qk.references]) {
      void client.invalidateQueries({ queryKey: key });
    }
  };
  // The table changed since it was read: reload it so a retry sends the new hash.
  const onError = (err: unknown) => {
    if (isApiError(err, "stale_write"))
      void client.invalidateQueries({ queryKey: qk.table(table) });
  };
  const path = { table };
  return {
    insert: useMutation({
      mutationFn: (body: Schemas["RowInsert"]) =>
        unwrap(api.POST("/api/data/{table}", { params: { path }, body })),
      onSuccess,
      onError,
    }),
    update: useMutation({
      mutationFn: (body: Schemas["RowUpdate"]) =>
        unwrap(api.PUT("/api/data/{table}", { params: { path }, body })),
      onSuccess,
      onError,
    }),
    remove: useMutation({
      mutationFn: (body: Schemas["RowDelete"]) =>
        unwrap(api.DELETE("/api/data/{table}", { params: { path }, body })),
      onSuccess,
      onError,
    }),
    rename: useMutation({
      mutationFn: (body: Schemas["RenameKeyRequest"]) =>
        unwrap(api.POST("/api/data/{table}/rename-key", { params: { path }, body })),
      onSuccess,
      onError,
    }),
  };
}

// --------------------------------------------------------------- build

export type BuildStatus = Schemas["BuildStatus"];

export const BUILD_POLL_MS = 1000;

export function useBuildTargets() {
  return useQuery({
    queryKey: qk.buildTargets,
    queryFn: () => unwrap(api.GET("/api/build/targets")),
    staleTime: Infinity,
  });
}

/** The latest build; polled every second while it runs. */
export function useBuildStatus() {
  const client = useQueryClient();
  return useQuery({
    queryKey: qk.build,
    queryFn: async () => {
      const previous = client.getQueryData<BuildStatus>(qk.build);
      const status = await unwrap(api.GET("/api/build/latest"));
      // A finished build changes which PDFs exist.
      if (previous?.state === "running" && status.state !== "running") {
        void client.invalidateQueries({ queryKey: qk.documents });
      }
      return status;
    },
    refetchInterval: (query) => (query.state.data?.state === "running" ? BUILD_POLL_MS : false),
  });
}

export function useStartBuild() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (target: string) =>
      unwrap(api.POST("/api/build/{target}", { params: { path: { target } } })),
    onSuccess: async (status) => {
      // An older in-flight poll must not overwrite the new running state.
      await client.cancelQueries({ queryKey: qk.build });
      client.setQueryData(qk.build, status);
    },
    onError: (err) => {
      // Someone else's build: show it.
      if (isApiError(err, "build_busy")) void client.invalidateQueries({ queryKey: qk.build });
    },
  });
}

// --------------------------------------------------------------- users

export function useUsers() {
  return useQuery({ queryKey: qk.users, queryFn: () => unwrap(api.GET("/api/users")) });
}

export function useUserWrites() {
  const client = useQueryClient();
  const onSuccess = () => void client.invalidateQueries({ queryKey: qk.users });
  return {
    create: useMutation({
      mutationFn: (body: Schemas["UserCreate"]) => unwrap(api.POST("/api/users", { body })),
      onSuccess,
    }),
    update: useMutation({
      mutationFn: ({ username, ...body }: Schemas["UserUpdate"] & { username: string }) =>
        unwrap(api.PATCH("/api/users/{username}", { params: { path: { username } }, body })),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: (username: string) =>
        unwrap(api.DELETE("/api/users/{username}", { params: { path: { username } } })),
      onSuccess,
    }),
  };
}
