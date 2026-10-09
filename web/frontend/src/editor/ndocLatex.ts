import type { languages } from "monaco-editor";

export const LANGUAGE_ID = "ndoc-latex";

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Monarch grammar for n-doc LaTeX: comments, commands, math and the n-doc
 * reference macros (from `GET /api/project/references`) as their own token. */
export function ndocLatexLanguage(referenceMacros: string[]): languages.IMonarchLanguage {
  const refs = [...referenceMacros].sort((a, b) => b.length - a.length).map(escapeRegExp);
  // Never matches when no macros are known yet.
  const reference = refs.length ? new RegExp(`\\\\(?:${refs.join("|")})(?![A-Za-z@])`) : /(?!)/;
  return {
    defaultToken: "",
    brackets: [
      { open: "{", close: "}", token: "delimiter.curly" },
      { open: "[", close: "]", token: "delimiter.square" },
    ],
    tokenizer: {
      root: [
        [/\\%/, "constant.character.escape"],
        [/%.*$/, "comment"],
        [reference, "keyword.reference"],
        [/\\(?:begin|end)(?![A-Za-z@])/, "keyword.environment"],
        [/\\[A-Za-z@]+\*?/, "keyword"],
        [/\\./, "constant.character.escape"],
        [/\$\$/, { token: "string.math", next: "@displayMath" }],
        [/\$/, { token: "string.math", next: "@math" }],
        [/[{}]/, "@brackets"],
        [/[[\]]/, "@brackets"],
      ],
      math: [
        [/\\./, "string.math"],
        [/\$/, { token: "string.math", next: "@pop" }],
        [/[^$\\]+/, "string.math"],
      ],
      displayMath: [
        [/\\./, "string.math"],
        [/\$\$/, { token: "string.math", next: "@pop" }],
        [/[^$\\]+|\$/, "string.math"],
      ],
    },
  };
}

export const ndocLatexConfiguration: languages.LanguageConfiguration = {
  comments: { lineComment: "%" },
  brackets: [
    ["{", "}"],
    ["[", "]"],
  ],
  autoClosingPairs: [
    { open: "{", close: "}" },
    { open: "[", close: "]" },
    { open: "$", close: "$" },
  ],
  surroundingPairs: [
    { open: "{", close: "}" },
    { open: "[", close: "]" },
    { open: "$", close: "$" },
  ],
  wordPattern: /\\?[A-Za-z@][A-Za-z@0-9_]*/,
};
