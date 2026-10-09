import Editor from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import { useReferences } from "../api/queries";
import type { SourceEditorProps } from "./editorTypes";
import { toMarkers } from "./markers";
import { monaco, setReferences } from "./monacoSetup";
import { LANGUAGE_ID } from "./ndocLatex";

function prefersDark() {
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export default function MonacoEditor({ path, value, onChange, issues, reveal }: SourceEditorProps) {
  const references = useReferences();
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (references.data) setReferences(references.data);
  }, [references.data]);

  useEffect(() => {
    const model = editorRef.current?.getModel();
    if (model) monaco.editor.setModelMarkers(model, "ndoc", toMarkers(issues, path));
  }, [issues, path, mounted]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || !reveal) return;
    editor.revealLineInCenter(reveal.line);
    editor.setSelection(new monaco.Range(reveal.line, 1, reveal.line + 1, 1));
    editor.focus();
  }, [reveal, mounted]);

  return (
    <Editor
      path={path}
      language={path.endsWith(".tex") ? LANGUAGE_ID : "plaintext"}
      value={value}
      onChange={(v) => onChange(v ?? "")}
      theme={prefersDark() ? "ndoc-dark" : "ndoc-light"}
      onMount={(editor) => {
        editorRef.current = editor;
        setMounted(true);
      }}
      options={{
        automaticLayout: true,
        wordWrap: "on",
        minimap: { enabled: false },
        fontSize: 13,
        renderWhitespace: "boundary",
        quickSuggestions: { other: true, comments: false, strings: true },
        unicodeHighlight: { ambiguousCharacters: false },
      }}
    />
  );
}
