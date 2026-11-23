import { Link } from "react-router-dom";
import { ProShell } from "@/features/pros/components/ProShell";
import { useProData } from "@/features/pros/hooks/useProData";
import { matchCount } from "@/features/pros/search";
import type { DoublesTournamentIndex, TournamentIndex } from "@/features/pros/types";
import { fetchDoublesTournamentIndex, fetchTournamentIndex } from "@/features/pros/proData";

type Edition = { id: string; name: string; season: number; singles: number; doubles: number };

function counts({ singles, doubles }: Edition): string {
  if (singles > 0 && doubles > 0) {
    return `${singles} singles · ${doubles} doubles matches in the data`;
  }
  if (doubles > 0) return `${doubles} doubles ${doubles === 1 ? "match" : "matches"} in the data`;
  return `${matchCount(singles)} in the data`;
}

function Seasons({ editions }: { editions: Edition[] }) {
  const seasons = [...new Set(editions.map((e) => e.season))].sort((a, b) => b - a);
  return (
    <>
      {seasons.map((season) => (
        <section key={season} aria-labelledby={`season-${season}`} className="mt-8">
          <h2 id={`season-${season}`} className="text-[18px] font-semibold">
            {season}
          </h2>
          <ul className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
            {editions
              .filter((e) => e.season === season)
              .map((e) => (
                <li key={e.id}>
                  <Link
                    to={`/tournaments/${encodeURIComponent(e.id)}`}
                    className="block min-h-11 rounded-2xl bg-card p-4 text-card-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    <span className="block font-semibold leading-tight">{e.name}</span>
                    <span className="mt-0.5 block text-sm text-muted-foreground">
                      {counts(e)}
                    </span>
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </>
  );
}

type IndexState<T> = ReturnType<typeof useProData<T>>;

function Body({
  singles,
  doubles,
}: {
  singles: IndexState<TournamentIndex>;
  doubles: IndexState<DoublesTournamentIndex>;
}) {
  if (singles.status === "loading" || doubles.status === "loading") {
    return <p className="py-8 text-sm text-muted-foreground">Loading…</p>;
  }
  // A missing file means that side has no data; any other failure is an error.
  const failed = [singles, doubles].some(
    (s) => s.status === "error" && s.error.kind !== "not-found",
  );
  if (failed) {
    return <p className="py-8 text-muted-foreground">Couldn't load tournaments.</p>;
  }
  const byId = new Map<string, Edition>();
  if (singles.status === "ready") {
    for (const e of singles.data.editions) {
      byId.set(e.id, { id: e.id, name: e.name, season: e.season, singles: e.matches, doubles: 0 });
    }
  }
  if (doubles.status === "ready") {
    for (const e of doubles.data.editions) {
      const have = byId.get(e.id);
      if (have) have.doubles = e.doublesMatches;
      else byId.set(e.id, { id: e.id, name: e.name, season: e.season, singles: 0, doubles: e.doublesMatches });
    }
  }
  const editions = [...byId.values()].sort(
    (a, b) => b.season - a.season || a.name.localeCompare(b.name),
  );
  return <Seasons editions={editions} />;
}

export default function TournamentsPage() {
  const singles = useProData(fetchTournamentIndex, []);
  const doubles = useProData(fetchDoublesTournamentIndex, []);
  const has = (s: { status: string; data?: { editions: unknown[] } }) =>
    s.status === "ready" && (s.data?.editions.length ?? 0) > 0;
  const source = has(singles) && has(doubles) ? "both" : has(doubles) ? "doubles" : "singles";
  return (
    <ProShell source={source}>
      <title>Tournaments | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Tournaments</h1>
      <p className="mt-2 text-muted-foreground">
        Selected matches, mostly later rounds. Not every match of each tournament.
      </p>
      <Body singles={singles} doubles={doubles} />
    </ProShell>
  );
}
