import { Link } from "react-router-dom";
import { ProShell } from "@/features/pros/components/ProShell";
import { useProData } from "@/features/pros/hooks/useProData";
import { matchCount } from "@/features/pros/search";
import { fetchTournamentIndex } from "@/features/pros/proData";
import type { TournamentEdition } from "@/features/pros/types";

function Seasons({ editions }: { editions: TournamentEdition[] }) {
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
                      {matchCount(e.matches)} in the data
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

function Body() {
  const state = useProData(fetchTournamentIndex, []);
  if (state.status === "loading") {
    return <p className="py-8 text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.status === "error") {
    return <p className="py-8 text-muted-foreground">Couldn't load tournaments.</p>;
  }
  return <Seasons editions={state.data.editions} />;
}

export default function TournamentsPage() {
  return (
    <ProShell>
      <title>Tournaments | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Tournaments</h1>
      <p className="mt-2 text-muted-foreground">
        Selected matches, mostly later rounds. Not every match of each tournament.
      </p>
      <Body />
    </ProShell>
  );
}
