import { pairName } from "../pairFormat";
import type { PairEvent, PairProfile } from "../types";
import { PlayerPhoto } from "./PlayerPhoto";
import { MatchFilter } from "./ProfileHeader";

type PairHeaderProps = {
  pair: PairProfile;
  viewId: string;
  onViewChange: (viewId: string) => void;
};

const eventNames: Record<PairEvent, string> = { MD: "Men's", WD: "Women's", XD: "Mixed" };

function contextLine(pair: PairProfile): string {
  const { matches, firstYear, lastYear, comparedWith } = pair.context;
  const n = `${matches} ${matches === 1 ? "match" : "matches"}`;
  const span = firstYear === lastYear ? `in ${firstYear}` : `from ${firstYear} to ${lastYear}`;
  const tail = pair.ranked
    ? `compared with ${comparedWith} other pairs.`
    : "not ranked: only one match in the data.";
  return `${eventNames[pair.event]} doubles. ${n} ${span}, ${tail}`;
}

function Tiles({ pair, size, radius, className }: { pair: PairProfile; size: number; radius: number; className: string }) {
  return (
    <div className={`flex shrink-0 gap-2 ${className}`}>
      {pair.players.map((p) => (
        <PlayerPhoto key={p.id} photo={null} name={p.name} size={size} radius={radius} />
      ))}
    </div>
  );
}

export function PairHeader({ pair, viewId, onViewChange }: PairHeaderProps) {
  const filtered = viewId !== "all";

  return (
    <header className="flex items-start justify-between gap-8 pb-8 max-[900px]:flex-col max-[900px]:gap-4">
      <div className="flex min-w-0 flex-1 items-start gap-8 max-[900px]:flex-col max-[900px]:gap-4">
        <Tiles pair={pair} size={88} radius={16} className="max-[900px]:hidden" />
        <Tiles pair={pair} size={64} radius={14} className="min-[901px]:hidden" />
        <div className="min-w-0">
          <h1 className="text-[48px] font-semibold leading-[1.05] tracking-[-0.035em] max-[900px]:text-[36px] max-[760px]:text-[30px]">
            {pairName(pair.players)}
          </h1>
          <p className="mt-2 text-muted-foreground">{contextLine(pair)}</p>
          {!filtered && pair.summary && (
            <p className="mt-4 max-w-[68ch] text-[19px] leading-normal text-foreground">
              {pair.summary}
            </p>
          )}
        </div>
      </div>

      <MatchFilter filters={pair.filters} viewId={viewId} onViewChange={onViewChange} />
    </header>
  );
}
