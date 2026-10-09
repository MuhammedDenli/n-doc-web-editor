import type { SourceEditorProps } from "../editor/editorTypes";

/** Stand-in for Monaco in jsdom. */
export default function TextareaEditor({ path, value, onChange, issues }: SourceEditorProps) {
  return (
    <>
      <textarea
        aria-label={`Source of ${path}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <output aria-label="markers">{issues.filter((i) => i.path === path).length}</output>
    </>
  );
}
