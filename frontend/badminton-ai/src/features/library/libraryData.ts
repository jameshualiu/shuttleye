import { collection, doc, getDoc, getDocs, query, where } from "firebase/firestore";
import { auth, db } from "@/lib/firebase";
import { err, ok, type Result } from "@/lib/result";
import type {
  LibraryIndex,
  LibraryPlayer,
  LibraryView,
  MatchDoc,
  UnpublishedMatch,
} from "./types";

export type LibraryError =
  | { kind: "not-found" }
  | { kind: "permission" }
  | { kind: "network"; message: string };

function toError(e: unknown): LibraryError {
  const code = (e as { code?: string } | null)?.code;
  if (code === "permission-denied") return { kind: "permission" };
  return { kind: "network", message: e instanceof Error ? e.message : "Network error" };
}

async function fetchDoc<T>(...path: [string, ...string[]]): Promise<Result<T, LibraryError>> {
  try {
    const snap = await getDoc(doc(db, path[0], ...path.slice(1)));
    if (!snap.exists()) return err({ kind: "not-found" });
    return ok(snap.data() as T);
  } catch (e) {
    return err(toError(e));
  }
}

export const fetchMatch = (id: string) => fetchDoc<MatchDoc>("matches", id);
export const fetchLibraryIndex = () => fetchDoc<LibraryIndex>("library", "index");
export const fetchLibraryPlayer = (id: string) => fetchDoc<LibraryPlayer>("players", id);
export const fetchLibraryView = (playerId: string, filterId: string) =>
  fetchDoc<LibraryView>("players", playerId, "views", filterId);

/** Admin only: matches awaiting publish. Non-admins get a permission error. */
export async function fetchUnpublishedMatches(): Promise<Result<UnpublishedMatch[], LibraryError>> {
  try {
    const snap = await getDocs(
      query(collection(db, "matches"), where("status", "==", "unpublished")),
    );
    return ok(
      snap.docs.map((d) => {
        const m = d.data() as MatchDoc;
        return {
          id: m.id,
          players: m.players,
          editionId: m.editionId,
          round: m.round,
          date: m.date,
          games: m.games,
          warnings: m.analyzer?.warnings?.length ?? 0,
        };
      }),
    );
  } catch (e) {
    return err(toError(e));
  }
}

/** True when the signed-in user has the `admin` custom claim. */
export async function isAdmin(): Promise<boolean> {
  try {
    const token = await auth.currentUser?.getIdTokenResult();
    return token?.claims.admin === true;
  } catch {
    return false;
  }
}
