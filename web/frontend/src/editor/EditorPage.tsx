import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { isApiError } from "../api/errors";
import {
  fetchFile,
  qk,
  useFile,
  useSaveFile,
  type CheckReport,
  type FileContent,
} from "../api/queries";
import { Dialog } from "../ui/Dialog";
import { ErrorText } from "../ui/ErrorText";
import { ConflictDialog } from "./ConflictDialog";
import { IssueList } from "./IssueList";
import { useDirtyGuard } from "./useDirtyGuard";

const MonacoEditor = lazy(() => import("./MonacoEditor"));

export function EditorPage() {
  const path = useParams()["*"] ?? "";
  if (!path) return <p className="muted pad">Select a file in the document tree.</p>;
  return <FileEditor key={path} path={path} />;
}

function FileEditor({ path }: { path: string }) {
  const file = useFile(path);
  if (file.isPending) return <p className="muted pad">Loading {path}…</p>;
  if (file.isError) return <ErrorText error={file.error} />;
  return <LoadedFile path={path} file={file.data} />;
}

function LoadedFile({ path, file }: { path: string; file: FileContent }) {
  const client = useQueryClient();
  const save = useSaveFile(path);
  const [text, setText] = useState(file.text);
  const [base, setBase] = useState({ text: file.text, sha: file.sha256 });
  const [checks, setChecks] = useState<CheckReport | null>(null);
  const [conflict, setConflict] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [reveal, setReveal] = useState<{ line: number; seq: number } | null>(null);
  const dirty = text !== base.text;
  const blocker = useDirtyGuard(dirty);

  const doSave = useCallback(
    (expected: string) => {
      const content = text;
      save.mutate(
        { content, expected_sha256: expected, create: false },
        {
          onSuccess: (result) => {
            setBase({ text: content, sha: result.sha256 });
            setChecks(result.checks ?? null);
            setConflict(false);
            client.setQueryData(qk.file(path), {
              ...file,
              text: content,
              sha256: result.sha256,
              size: result.size,
            });
          },
          onError: (err) => {
            if (isApiError(err, "stale_write")) setConflict(true);
          },
        },
      );
    },
    [text, save, client, path, file],
  );

  // Ctrl+S / Cmd+S anywhere on the page (Monaco has no binding of its own).
  const saveRef = useRef(() => {});
  saveRef.current = () => {
    if (dirty && !save.isPending) doSave(base.sha);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function reloadFromServer() {
    setReloading(true);
    try {
      const fresh = await fetchFile(path);
      client.setQueryData(qk.file(path), fresh);
      setText(fresh.text);
      setBase({ text: fresh.text, sha: fresh.sha256 });
      setChecks(null);
      setConflict(false);
      save.reset();
    } finally {
      setReloading(false);
    }
  }

  async function overwrite() {
    const err = save.error;
    const current =
      isApiError(err, "stale_write") && typeof err.details.current_hash === "string"
        ? err.details.current_hash
        : (await fetchFile(path)).sha256;
    doSave(current);
  }

  const saveError = save.error && !isApiError(save.error, "stale_write") ? save.error : null;

  return (
    <div className="editor-page">
      <div className="editor-bar">
        <span className="file-path" title={path}>
          {path}
          {dirty && <span aria-label="unsaved changes"> ●</span>}
        </span>
        <span className="spacer" />
        {checks && !checks.ok && (
          <span className="error">
            {checks.issues.length} issue{checks.issues.length === 1 ? "" : "s"}
          </span>
        )}
        <button
          className="primary"
          onClick={() => doSave(base.sha)}
          disabled={!dirty || save.isPending}
          title="Save (Ctrl+S)"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
      <ErrorText error={saveError} />
      <div className="editor-host">
        <Suspense fallback={<p className="muted pad">Loading editor…</p>}>
          <MonacoEditor
            path={path}
            value={text}
            onChange={setText}
            issues={checks?.issues ?? []}
            reveal={reveal}
          />
        </Suspense>
      </div>
      {checks && (
        <IssueList
          checks={checks}
          path={path}
          onReveal={(line) => setReveal((r) => ({ line, seq: (r?.seq ?? 0) + 1 }))}
        />
      )}
      <ConflictDialog
        open={conflict}
        busy={save.isPending || reloading}
        onReload={() => void reloadFromServer()}
        onOverwrite={() => void overwrite()}
        onCancel={() => setConflict(false)}
      />
      <Dialog
        open={blocker.state === "blocked"}
        title="Unsaved changes"
        onClose={() => blocker.reset?.()}
      >
        <p>{path} has unsaved changes. Leave and discard them?</p>
        <div className="actions">
          <button onClick={() => blocker.reset?.()}>Stay</button>
          <button className="danger" onClick={() => blocker.proceed?.()}>
            Discard changes
          </button>
        </div>
      </Dialog>
    </div>
  );
}
