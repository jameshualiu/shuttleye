import { Link } from "react-router-dom";
import { nationalities, pairName } from "../pairFormat";
import { matchCount } from "../search";
import type { PairIndexEntry } from "../types";
import { PlayerPhoto } from "./PlayerPhoto";

export function PairCard({ pair }: { pair: PairIndexEntry }) {
  return (
    <Link
      to={`/pairs/${encodeURIComponent(pair.id)}`}
      className="flex min-h-11 items-center gap-4 rounded-2xl border border-border bg-card p-4 text-card-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <span className="flex shrink-0 gap-1">
        {pair.players.map((p) => (
          <PlayerPhoto key={p.id} photo={null} name={p.name} size={44} radius={10} decorative />
        ))}
      </span>
      <span className="min-w-0">
        <span className="block font-semibold leading-tight">{pairName(pair.players)}</span>
        <span className="mt-0.5 block text-sm text-foreground/80">
          {nationalities(pair.players)} · {matchCount(pair.matches)}
        </span>
        {!pair.ranked && (
          <span className="mt-0.5 block text-sm text-muted-foreground">Not enough data to rank</span>
        )}
      </span>
    </Link>
  );
}
