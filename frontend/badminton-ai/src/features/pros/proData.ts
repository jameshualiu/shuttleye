import { err, ok, type Result } from "@/lib/result";
import type {
  PlayerIndex,
  PlayerProfile,
  Tournament,
  TournamentIndex,
} from "./types";

export type ProDataError =
  | { kind: "not-found" }
  | { kind: "network"; message: string };

async function fetchJson<T>(path: string): Promise<Result<T, ProDataError>> {
  try {
    const res = await fetch(`/pro-data/${path}`);
    if (res.status === 404) return err({ kind: "not-found" });
    if (!res.ok) return err({ kind: "network", message: `Request failed (${res.status})` });
    // Vite's SPA fallback serves index.html for unknown paths.
    const type = res.headers.get("content-type") ?? "";
    if (!type.includes("json")) return err({ kind: "not-found" });
    return ok((await res.json()) as T);
  } catch (e) {
    return err({ kind: "network", message: e instanceof Error ? e.message : "Network error" });
  }
}

const seg = (id: string) => encodeURIComponent(id);

export const fetchPlayerIndex = () => fetchJson<PlayerIndex>("players/index.json");
export const fetchPlayer = (id: string) => fetchJson<PlayerProfile>(`players/${seg(id)}.json`);
export const fetchTournamentIndex = () => fetchJson<TournamentIndex>("tournaments/index.json");
export const fetchTournament = (id: string) => fetchJson<Tournament>(`tournaments/${seg(id)}.json`);
