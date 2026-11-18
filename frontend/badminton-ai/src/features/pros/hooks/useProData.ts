import { useEffect, useState } from "react";
import type { Result } from "@/lib/result";
import type { ProDataError } from "../proData";

export type ProDataState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: ProDataError };

/** Runs `load` on mount and whenever `deps` change. Stale responses are ignored. */
export function useProData<T>(
  load: () => Promise<Result<T, ProDataError>>,
  deps: unknown[],
): ProDataState<T> {
  const [state, setState] = useState<ProDataState<T>>({ status: "loading" });

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
