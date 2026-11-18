import { Link, useParams } from "react-router-dom";
import { ProShell } from "@/features/pros/components/ProShell";
import { Panel } from "@/features/pros/components/Panel";
import { PlayerCard } from "@/features/pros/components/PlayerCard";
import { useProData } from "@/features/pros/hooks/useProData";
import { fetchPlayerIndex, fetchTournament } from "@/features/pros/proData";
import type { PlayerIndexEntry, Tournament } from "@/features/pros/types";

const linkClass =
  "inline-flex min-h-11 items-center rounded-md font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/** Winner's score first in each game: "21–15, 18–21, 21–12". */
function formatGames(games: [number, number][]): string {
  return games.map(([w, l]) => `${w}–${l}`).join(", ");
}

function Detail({ tournament }: { tournament: Tournament }) {
  const photos = useProData(fetchPlayerIndex, []);
  const index = new Map<string, PlayerIndexEntry>();
  if (photos.status === "ready") photos.data.players.forEach((p) => index.set(p.id, p));
  const viewTo = (id: string) => `/players/${encodeURIComponent(id)}?view=t:${encodeURIComponent(tournament.id)}`;

  return (
    <>
      <title>{`${tournament.name} ${tournament.season} | Shuttleye`}</title>
      <Link to="/tournaments" className="text-sm text-muted-foreground hover:text-foreground">
        All tournaments
      </Link>
      <h1 className="mt-2 text-[32px] font-semibold tracking-tight">{tournament.name}</h1>
      <p className="mt-1 text-muted-foreground">{tournament.season}</p>

      <div className="mt-8 grid gap-6">
        <Panel title="Matches">
          <ul className="divide-y divide-border">
            {tournament.matches.map((m) => (
              <li
                key={m.id}
                className="grid grid-cols-[110px_1fr_auto] items-center gap-x-4 gap-y-0 py-1 max-[760px]:grid-cols-1"
              >
                <span className="text-sm text-muted-foreground">{m.round}</span>
                <span>
                  <Link to={viewTo(m.winner.id)} className={`${linkClass} font-semibold`}>
                    {m.winner.name}
                  </Link>
                  <span className="text-muted-foreground"> beat </span>
                  <Link to={viewTo(m.loser.id)} className={linkClass}>
                    {m.loser.name}
                  </Link>
                </span>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {formatGames(m.games)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Players">
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
            {tournament.players.map((p) => (
              <li key={p.id}>
                <PlayerCard to={viewTo(p.id)} name={p.name} photo={index.get(p.id)?.photo ?? null} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}

function NotFound() {
  return (
    <div className="py-16">
      <title>Tournament not found | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Not found</h1>
      <p className="mt-2 text-muted-foreground">We don't have this tournament.</p>
      <Link
        to="/tournaments"
        className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        See all tournaments
      </Link>
    </div>
  );
}

function Loader({ editionId }: { editionId: string }) {
  const state = useProData(() => fetchTournament(editionId), [editionId]);
  if (state.status === "loading") {
    return <p className="py-16 text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.status === "error") {
    if (state.error.kind === "not-found") return <NotFound />;
    return (
      <p className="py-16 text-muted-foreground">
        Couldn't load this tournament. {state.error.message}
      </p>
    );
  }
  if (state.data.id !== editionId) return <NotFound />;
  return <Detail tournament={state.data} />;
}

export default function TournamentPage() {
  const { editionId = "" } = useParams();
  return (
    <ProShell>
      <Loader key={editionId} editionId={editionId} />
    </ProShell>
  );
}
