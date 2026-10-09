import { isApiError } from "../api/errors";
import { useBuildStatus, useBuildTargets, useStartBuild } from "../api/queries";
import { useActiveDocument } from "../shell/activeDocument";

/** Top bar: build the active document, or the delivery. */
export function BuildControls() {
  const { document } = useActiveDocument();
  const targets = useBuildTargets().data ?? [];
  const status = useBuildStatus().data;
  const start = useStartBuild();
  const running = status?.state === "running" || start.isPending;
  const choices = [document, "delivery"].filter((t): t is string => !!t && targets.includes(t));

  return (
    <span className="build-controls">
      {choices.map((target) => (
        <button key={target} onClick={() => start.mutate(target)} disabled={running}>
          Build {target}
        </button>
      ))}
      {running && <span className="muted">building {status?.target ?? ""}…</span>}
      {isApiError(start.error, "build_busy") && (
        <span className="error" role="alert">
          Another build is running.
        </span>
      )}
      {start.error && !isApiError(start.error, "build_busy") && (
        <span className="error" role="alert">
          {start.error.message}
        </span>
      )}
    </span>
  );
}
