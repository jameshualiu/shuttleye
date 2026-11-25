import { Link, useParams } from "react-router-dom";
import { ProShell } from "@/features/pros/components/ProShell";
import { Panel } from "@/features/pros/components/Panel";
import { PlayerCard } from "@/features/pros/components/PlayerCard";
import { useProData } from "@/features/pros/hooks/useProData";
import {
  fetchDoublesTournament,
  fetchPlayerIndex,
  fetchTournament,
} from "@/features/pros/proData";
import { eventLabels } from "@/features/pros/pairFormat";
import type {
  DoublesTournament,
  PlayerIndexEntry,
  Tournament,
} from "@/features/pros/types";

const linkClass =
  "inline-flex min-h-11 items-center rounded-md font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/** Winner's score first in each game: "21–15, 18–21, 21–12". A set whose
 * recorded score isn't a finished game says so instead of being padded. */
function formatGames(games: [number, number][], incomplete: number[]): string {
  return games
    .map(([w, l], i) => (incomplete.includes(i) ? `${w}–${l} (incomplete in the data)` : `${w}–${l}`))
    .join(", ");
}

function DoublesSections({ tournament }: { tournament: DoublesTournament }) {
  const viewTo = (id: string) => `/pairs/${encodeURIComponent(id)}?view=t:${encodeURIComponent(tournament.id)}`;
  return (
    <>
      <Panel title="Doubles matches">
        <ul className="divide-y divide-border">
          {tournament.matches.map((m) => (
            <li
              key={m.id}
              className="grid grid-cols-[170px_1fr_auto] items-center gap-x-4 gap-y-0 py-1 max-[760px]:grid-cols-1"
            >
              <span className="text-sm text-muted-foreground">
                {eventLabels[m.event]} · {m.round}
              </span>
              <span>
                <Link to={viewTo(m.winner.id)} className={`${linkClass} font-semibold`}>
                  {m.winner.names}
                </Link>
                <span className="text-muted-foreground"> beat </span>
                <Link to={viewTo(m.loser.id)} className={linkClass}>
                  {m.loser.names}
                </Link>
              </span>
              <span className="text-sm tabular-nums text-muted-foreground">
                {formatGames(m.games, m.incomplete)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Doubles pairs">
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {tournament.pairs.map((p) => (
            <li key={p.id}>
              <Link
                to={viewTo(p.id)}
                className="block min-h-11 rounded-2xl border border-border bg-card p-4 text-card-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <span className="block font-semibold leading-tight">{p.names}</span>
                <span className="mt-0.5 block text-sm text-foreground/80">{eventLabels[p.event]}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

function SinglesSections({ tournament }: { tournament: Tournament }) {
  const photos = useProData(fetchPlayerIndex, []);
  const index = new Map<string, PlayerIndexEntry>();
  if (photos.status === "ready") photos.data.players.forEach((p) => index.set(p.id, p));
  const viewTo = (id: string) => `/players/${encodeURIComponent(id)}?view=t:${encodeURIComponent(tournament.id)}`;

  return (
    <>
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
                  {formatGames(m.games, m.incomplete)}
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

type Sides = { singles: Tournament | null; doubles: DoublesTournament | null };

function Detail({ singles, doubles }: Sides) {
  const head = (singles ?? doubles)!;
  return (
    <>
      <title>{`${head.name} ${head.season} | Shuttleye`}</title>
      <Link to="/tournaments" className="text-sm text-muted-foreground hover:text-foreground">
        All tournaments
      </Link>
      <h1 className="mt-2 text-[32px] font-semibold tracking-tight">{head.name}</h1>
      <p className="mt-1 text-muted-foreground">{head.season}</p>
      <div className="mt-8 grid gap-6">
        {singles && singles.matches.length > 0 && <SinglesSections tournament={singles} />}
        {doubles && doubles.matches.length > 0 && <DoublesSections tournament={doubles} />}
      </div>
    </>
  );
}

function Loader({ editionId }: { editionId: string }) {
  return <Resolved editionId={editionId} />;
}

function Resolved({ editionId }: { editionId: string }) {
  const singles = useProData(() => fetchTournament(editionId), [editionId]);
  const doubles = useProData(() => fetchDoublesTournament(editionId), [editionId]);
  if (singles.status === "loading" || doubles.status === "loading") {
    return <ProShell><p className="py-16 text-sm text-muted-foreground">Loading…</p></ProShell>;
  }
  // A missing file means that side has no data; any other failure is an error.
  for (const s of [singles, doubles]) {
    if (s.status === "error" && s.error.kind === "network") {
      return (
        <ProShell>
          <p className="py-16 text-muted-foreground">
            Couldn't load this tournament. {s.error.message}
          </p>
        </ProShell>
      );
    }
  }
  const s = singles.status === "ready" && singles.data.id === editionId ? singles.data : null;
  const d = doubles.status === "ready" && doubles.data.id === editionId ? doubles.data : null;
  if (!s && !d) {
    return (
      <ProShell>
        <NotFound />
      </ProShell>
    );
  }
  const hasSingles = !!s && s.matches.length > 0;
  const hasDoubles = !!d && d.matches.length > 0;
  const source = hasSingles && hasDoubles ? "both" : hasDoubles ? "doubles" : "singles";
  return (
    <ProShell source={source}>
      <Detail singles={s} doubles={d} />
    </ProShell>
  );
}

export default function TournamentPage() {
  const { editionId = "" } = useParams();
  return <Loader key={editionId} editionId={editionId} />;
}
