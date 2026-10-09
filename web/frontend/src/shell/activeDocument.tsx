import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

const KEY = "ndoc.activeDocument";

interface ActiveDocument {
  document: string | null;
  setDocument: (name: string) => void;
}

const Context = createContext<ActiveDocument>({ document: null, setDocument: () => {} });

function stored(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** The document chosen in the tree; it is also the default build target. */
export function ActiveDocumentProvider({ children }: { children: ReactNode }) {
  const [document, setState] = useState<string | null>(stored);
  const setDocument = useCallback((name: string) => {
    setState(name);
    try {
      localStorage.setItem(KEY, name);
    } catch {
      // per-browser convenience only
    }
  }, []);
  return <Context.Provider value={{ document, setDocument }}>{children}</Context.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useActiveDocument() {
  return useContext(Context);
}
