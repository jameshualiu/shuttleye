import { ok } from "@/lib/result";
import { fetchLibraryIndex } from "../libraryData";
import type { LibraryIndex } from "../types";
import { useLibraryDoc } from "./useLibraryDoc";

/** The library index. DEV ONLY: with `fixture` set it loads the bundled fixture instead of
 *  Firestore (the branch and the fixture chunk are dropped from production builds). */
export function useLibraryIndex(fixture: boolean) {
  return useLibraryDoc(() => {
    if (import.meta.env.DEV && fixture) {
      return import("../__fixtures__/library.json").then((m) =>
        ok(m.default.index as unknown as LibraryIndex),
      );
    }
    return fetchLibraryIndex();
  }, [fixture]);
}
