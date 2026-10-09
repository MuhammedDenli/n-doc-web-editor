import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "./client";
import { isApiError, unwrap } from "./errors";

export type User = Schemas["User"];

export const qk = {
  me: ["me"] as const,
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
