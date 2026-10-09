// Monaco is bundled locally (no CDN) and only loaded with the editor chunk.
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/editor/editor.worker?worker";
import { loader } from "@monaco-editor/react";
import type { References } from "../api/queries";
import { completionContext, completionItems } from "./completion";
import { LANGUAGE_ID, ndocLatexConfiguration, ndocLatexLanguage } from "./ndocLatex";

self.MonacoEnvironment = { getWorker: () => new editorWorker() };
loader.config({ monaco });

let references: References = { macros: {}, keys: {} };

monaco.languages.register({ id: LANGUAGE_ID, extensions: [".tex"] });
monaco.languages.setLanguageConfiguration(LANGUAGE_ID, ndocLatexConfiguration);
monaco.languages.setMonarchTokensProvider(LANGUAGE_ID, ndocLatexLanguage([]));

monaco.languages.registerCompletionItemProvider(LANGUAGE_ID, {
  triggerCharacters: ["{", "."],
  provideCompletionItems(model, position) {
    const line = model.getLineContent(position.lineNumber).slice(0, position.column - 1);
    const ctx = completionContext(line, references.macros);
    if (!ctx) return { suggestions: [] };
    const range = new monaco.Range(
      position.lineNumber,
      position.column - ctx.prefix.length,
      position.lineNumber,
      position.column,
    );
    return {
      suggestions: completionItems(ctx, references).map((item) => ({
        label: item.label,
        detail: item.detail,
        kind: monaco.languages.CompletionItemKind.Reference,
        insertText: item.label,
        filterText: item.label,
        range,
      })),
    };
  },
});

/** New reference data: macro highlighting and completion follow `common/db`. */
export function setReferences(refs: References) {
  const changed =
    Object.keys(refs.macros).join() !== Object.keys(references.macros).join() ||
    !Object.keys(references.macros).length;
  references = refs;
  if (changed) {
    monaco.languages.setMonarchTokensProvider(
      LANGUAGE_ID,
      ndocLatexLanguage(Object.keys(refs.macros)),
    );
  }
}

const rules = (dark: boolean): monaco.editor.ITokenThemeRule[] => [
  { token: "keyword.reference", foreground: dark ? "4fc1ff" : "0b62c4", fontStyle: "bold" },
  { token: "keyword.environment", foreground: dark ? "c586c0" : "8a3b9e" },
  { token: "string.math", foreground: dark ? "ce9178" : "a3501c" },
];
monaco.editor.defineTheme("ndoc-light", {
  base: "vs",
  inherit: true,
  rules: rules(false),
  colors: {},
});
monaco.editor.defineTheme("ndoc-dark", {
  base: "vs-dark",
  inherit: true,
  rules: rules(true),
  colors: {},
});

export { monaco };
