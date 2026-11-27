import { Link } from "react-router-dom";
import { editionName, scoreText } from "../names";
import type { LibraryPlayerRef, MatchDoc } from "../types";

const nameLink =
  "rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

function PlayerLink({ player, className }: { player: LibraryPlayerRef; className?: string }) {
  return (
    <Link to={`/library/players/${player.id}`} className={`${nameLink} ${className ?? ""}`}>
      {player.name}
    </Link>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[72px] rounded-xl bg-card px-3 py-2 text-center">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function MatchHeader({ match, editionLabel }: { match: MatchDoc; editionLabel?: string }) {
  // A is always the match winner (data-flow.md section 8).
  const winner = match.players.A;
  const loser = match.players.B;
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm text-muted-foreground">
          Library / {editionLabel ?? editionName(match.editionId)} / {match.round}
        </p>
        <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight max-[600px]:text-[22px]">
          <PlayerLink player={winner} />{" "}
          <span className="font-medium text-muted-foreground">
            d. <PlayerLink player={loser} />
          </span>
        </h1>
      </div>
      <div className="flex flex-wrap gap-2">
        {match.games ? (
          match.games.map((g, i) => <Tile key={i} label={`Game ${i + 1}`} value={scoreText(g)} />)
        ) : (
          <Tile label="Score" value="Not read" />
        )}
        <Tile label="Rallies" value={String(match.summary.rallies)} />
        <Tile label="Avg shots" value={match.summary.avgShots.toFixed(1)} />
      </div>
    </header>
  );
}
