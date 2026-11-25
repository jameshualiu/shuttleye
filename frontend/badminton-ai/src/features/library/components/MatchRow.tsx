import { Link } from "react-router-dom";
import { editionName } from "../names";
import type { GameScore, LibraryPlayerRef, Side } from "../types";

export type MatchRowData = {
  id: string;
  editionId: string;
  round: string;
  date: string;
  players: Record<Side, LibraryPlayerRef>;
  games: GameScore[] | null;
};

function gamesText(games: GameScore[] | null): string {
  return games && games.length > 0 ? games.map((g) => `${g.a}–${g.b}`).join(", ") : "Score not read";
}

/** One match: "Winner d. Loser", then tournament round · year, games on the right. A is the winner. */
export function MatchRow({
  match,
  editionLabel,
  year,
  note,
}: {
  match: MatchRowData;
  /** The edition's name from the library index; falls back to a name built from the id. */
  editionLabel?: string;
  year: number | string;
  note?: string;
}) {
  return (
    <Link
      to={`/matches/${match.id}`}
      className="grid min-h-11 grid-cols-[1fr_auto] items-center gap-x-4 gap-y-0.5 rounded-xl px-4 py-3 transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring max-[600px]:grid-cols-1"
    >
      <span className="min-w-0">
        <span className="font-semibold">{match.players.A.name}</span>
        <span className="text-muted-foreground"> d. </span>
        <span className="font-medium">{match.players.B.name}</span>
      </span>
      <span className="text-sm tabular-nums text-muted-foreground max-[600px]:row-start-3">
        {gamesText(match.games)}
      </span>
      <span className="text-sm text-muted-foreground">
        {editionLabel ?? editionName(match.editionId)} {match.round} · {year}
        {note ? ` · ${note}` : ""}
      </span>
    </Link>
  );
}
