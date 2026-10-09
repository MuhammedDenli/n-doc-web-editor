import type { Schemas } from "../api/client";

export const admin: Schemas["User"] = { username: "alice", role: "admin", disabled: false };
export const editor: Schemas["User"] = { username: "bob", role: "editor", disabled: false };
