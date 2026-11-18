import type { ShotRow } from "../types";
import { Panel } from "./Panel";

type ShotChoicePanelProps = {
  rows: ShotRow[];
  shots: number;
  /** True in the all-matches view, where ranks are shown. */
  ranked: boolean;
  pronoun: { he: string; his: string };
  className?: string;
};

function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

function rankWidth(rank: number, of: number): number {
  return of > 1 ? ((of - rank) / (of - 1)) * 100 : 100;
}

export function ShotChoicePanel({ rows, shots, ranked, pronoun, className }: ShotChoicePanelProps) {
  const of = rows.find((r) => r.of !== null)?.of ?? null;
  const showRanks = ranked && of !== null;
  const shotCount = shots.toLocaleString("en-US");
  const subtitle = !ranked
    ? `Share of ${shotCount} shots in this selection`
    : showRanks
      ? `Share of ${pronoun.his} ${shotCount} shots, ranked against ${of} pros`
      : `Share of ${pronoun.his} ${shotCount} shots`;

  return (
    <Panel title="Shot choice" subtitle={subtitle} className={className}>
      <div
        className="grid grid-flow-col gap-x-16 gap-y-3.5 min-[761px]:grid-cols-2 max-[760px]:grid-flow-row"
        style={{ gridTemplateRows: `repeat(${Math.ceil(rows.length / 2)}, auto)` }}
      >
        {rows.map((r) =>
          showRanks && r.rank !== null && r.of !== null ? (
            <div
              key={r.group}
              className="grid grid-cols-[64px_60px_1fr_84px] items-center gap-4 text-[15px] max-[900px]:grid-cols-[56px_52px_1fr] max-[900px]:gap-y-1"
            >
              <span>{r.group}</span>
              <span className="text-right font-semibold tabular-nums">{r.share.toFixed(1)}%</span>
              <div className="h-2 overflow-hidden rounded bg-muted-foreground/15">
                <div
                  className="h-full rounded bg-foreground"
                  style={{ width: `${rankWidth(r.rank, r.of)}%` }}
                />
              </div>
              <span className="text-sm tabular-nums text-muted-foreground max-[900px]:col-start-3">
                {ordinal(r.rank)} of {r.of}
              </span>
            </div>
          ) : (
            <div
              key={r.group}
              className="grid grid-cols-[64px_60px_88px_1fr] items-center gap-4 text-[15px] max-[900px]:grid-cols-[56px_52px_1fr] max-[900px]:gap-y-1"
            >
              <span>{r.group}</span>
              <span className="text-right font-semibold tabular-nums">{r.share.toFixed(1)}%</span>
              <span className="text-sm tabular-nums text-muted-foreground">
                {r.count.toLocaleString("en-US")} shots
              </span>
              <span className="text-sm tabular-nums text-muted-foreground max-[900px]:col-start-3">
                Typical pro {r.typical.toFixed(1)}%
              </span>
            </div>
          ),
        )}
      </div>
      {showRanks && (
        <p className="mt-6 max-w-[75ch] text-sm text-muted-foreground">
          A longer bar means {pronoun.he} plays that shot more often than most pros. It's about
          style, not skill.
        </p>
      )}
    </Panel>
  );
}
