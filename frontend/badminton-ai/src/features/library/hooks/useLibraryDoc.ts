import { useEffect, useState } from "react";
import type { Result } from "@/lib/result";
import type { LibraryError } from "../libraryData";

export type LibraryDocState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: LibraryError };

/** Runs `load` on mount and whenever `deps` change. Stale responses are ignored. */
export function useLibraryDoc<T>(
  load: () => Promise<Result<T, LibraryError>>,
  deps: unknown[],
): LibraryDocState<T> {
  const [state, setState] = useState<LibraryDocState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    load().then((result) => {
      if (cancelled) return;
      setState(
        result.ok
          ? { status: "ready", data: result.value }
          : { status: "error", error: result.error },
      );
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
