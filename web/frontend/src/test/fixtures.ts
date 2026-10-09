import type { Schemas } from "../api/client";

export const admin: Schemas["User"] = { username: "alice", role: "admin", disabled: false };
export const editor: Schemas["User"] = { username: "bob", role: "editor", disabled: false };

export const documents: Schemas["Document"][] = [
  {
    name: "adv_tds",
    kind: "pdf",
    main_file: "adv_tds/adv_tds.tex",
    pdf_file: "adv_tds/adv_tds.pdf",
    pdf_exists: true,
  },
  {
    name: "mwe_tds",
    kind: "mwe",
    main_file: "mwe_tds/mwe_tds.tex",
    pdf_file: "mwe_tds/mwe_tds.pdf",
    pdf_exists: false,
  },
];

export const tree: Schemas["InputNode"] = {
  path: "adv_tds/adv_tds.tex",
  exists: true,
  children: [
    { path: "adv_tds/module/tls/core.tex", exists: true, children: [], line: 12 },
    { path: "adv_tds/missing.tex", exists: false, children: [], line: 13, note: "not found" },
  ],
};

export const references: Schemas["References"] = {
  macros: { sfrlink: "sfr" },
  keys: { sfr: [{ key: "FCS_CKM.1", name: "Key generation" }] },
};

export function fileContent(path: string, text: string, sha256 = "sha-1"): Schemas["FileContent"] {
  return { path, text, sha256, size: text.length };
}
