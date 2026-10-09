import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useDocuments, useDocumentTree, type InputNode } from "../api/queries";
import { useActiveDocument } from "../shell/activeDocument";
import { ErrorText } from "../ui/ErrorText";

function fileName(path: string) {
  return path.slice(path.lastIndexOf("/") + 1);
}

function TreeNode({ node, depth }: { node: InputNode; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const children = node.children ?? [];
  const hasChildren = children.length > 0;
  return (
    <li>
      <div className="tree-row">
        {hasChildren ? (
          <button
            className="twisty"
            aria-label={open ? "Collapse" : "Expand"}
            onClick={() => setOpen(!open)}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="twisty" />
        )}
        {node.exists ? (
          <NavLink to={`/edit/${node.path}`} title={node.path}>
            {fileName(node.path)}
          </NavLink>
        ) : (
          <span className="missing" title={node.note ?? `${node.path} does not exist`}>
            {fileName(node.path)}
          </span>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {children.map((child, i) => (
            <TreeNode key={`${child.path}:${child.line ?? i}`} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** Document picker and the `\input` tree of the active document. */
export function DocumentTree() {
  const documents = useDocuments();
  const { document, setDocument } = useActiveDocument();
  const tree = useDocumentTree(document);

  // Default (or a stored name that no longer exists): the first document.
  const docs = documents.data;
  useEffect(() => {
    if (docs?.length && !docs.some((d) => d.name === document)) setDocument(docs[0]!.name);
  }, [docs, document, setDocument]);

  return (
    <div className="doc-tree">
      <label>
        Document
        <select value={document ?? ""} onChange={(e) => setDocument(e.target.value)}>
          {documents.data?.map((d) => (
            <option key={d.name} value={d.name}>
              {d.name}
              {d.kind === "mwe" ? " (test)" : ""}
            </option>
          ))}
        </select>
      </label>
      <ErrorText error={documents.error ?? tree.error} />
      {tree.data && (
        <ul className="tree">
          <TreeNode node={tree.data} depth={0} />
        </ul>
      )}
    </div>
  );
}
