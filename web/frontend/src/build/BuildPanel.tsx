import { useEffect, useState } from "react";
import { useBuildStatus, useDocuments, type BuildStatus } from "../api/queries";
import { useActiveDocument } from "../shell/activeDocument";
import { ErrorText } from "../ui/ErrorText";

type View = "pdf" | "log";

function StatusLine({ status }: { status: BuildStatus }) {
  if (status.state === "idle") return <span className="muted">No build yet</span>;
  const elapsed = status.elapsed_s != null ? ` · ${Math.round(status.elapsed_s)} s` : "";
  const label = {
    running: "running",
    succeeded: "succeeded",
    failed: status.timed_out ? "timed out" : "failed",
  }[status.state];
  const tone = { running: "muted", succeeded: "ok", failed: "error" }[status.state];
  return (
    <span className={tone} role="status">
      {status.target} {label}
      {elapsed}
    </span>
  );
}

function BuildLog({ status }: { status: BuildStatus }) {
  const errors = status.errors ?? [];
  return (
    <div className="build-log">
      {status.error && <ErrorText error={status.error.message} />}
      {errors.length > 0 && (
        <ul className="error" aria-label="Build errors">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      {status.pdf_checks && status.pdf_checks.issues.length > 0 && (
        <ul className="warning" aria-label="PDF checks">
          {status.pdf_checks.issues.map((i, n) => (
            <li key={n}>
              {i.path}: {i.message}
            </li>
          ))}
        </ul>
      )}
      <pre aria-label="Build log">{(status.log_tail ?? []).join("\n")}</pre>
    </div>
  );
}

/** Right panel: the active document's PDF and the latest build's log. */
export function BuildPanel() {
  const { document } = useActiveDocument();
  const status = useBuildStatus();
  const documents = useDocuments();
  const [view, setView] = useState<View>("pdf");
  const state = status.data?.state;

  // Follow the build: log while it runs or after it failed, PDF after success.
  useEffect(() => {
    if (state === "running" || state === "failed") setView("log");
    if (state === "succeeded") setView("pdf");
  }, [state]);

  const doc = documents.data?.find((d) => d.name === document);
  // Bust the browser cache after every build (the response is no-store anyway).
  const version = status.data?.started_at ?? 0;

  return (
    <>
      <div className="panel-bar">
        <nav className="tabs" aria-label="Panel">
          <button className={view === "pdf" ? "active" : ""} onClick={() => setView("pdf")}>
            PDF
          </button>
          <button className={view === "log" ? "active" : ""} onClick={() => setView("log")}>
            Build log
          </button>
        </nav>
        <span className="spacer" />
        {status.data && <StatusLine status={status.data} />}
      </div>
      <ErrorText error={status.error} />
      {view === "log" &&
        (status.data && status.data.state !== "idle" ? (
          <BuildLog status={status.data} />
        ) : (
          <p className="muted pad">No build has run on this server yet.</p>
        ))}
      {view === "pdf" &&
        (doc?.pdf_exists ? (
          <iframe
            className="pdf"
            title={`${doc.name} PDF`}
            src={`/api/preview/${encodeURIComponent(doc.name)}?v=${version}`}
          />
        ) : (
          <p className="muted pad">
            {doc ? `${doc.name} has not been built yet.` : "Choose a document."}
          </p>
        ))}
    </>
  );
}
