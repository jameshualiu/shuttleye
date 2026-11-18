import type { BandRow } from "../types";
import { Panel } from "./Panel";

type RallyLengthPanelProps = {
  bands: BandRow[];
  rallies: number;
  playerName: string;
  className?: string;
};

function Label({ text }: { text: string }) {
  return (
    <span className="max-w-36 truncate text-muted-foreground" title={text}>
      {text}
    </span>
  );
}

function Bar({ value, typical }: { value: number; typical?: boolean }) {
  return (
    <>
      <div className="h-2 overflow-hidden rounded bg-muted-foreground/15">
        <div
          className={typical ? "h-full rounded bg-muted-foreground/50" : "h-full rounded bg-foreground"}
          style={{ width: `${value}%` }}
        />
      </div>
      <span
        className={
          typical
            ? "text-right font-medium tabular-nums text-muted-foreground"
            : "text-right font-semibold tabular-nums"
        }
      >
        {value}%
      </span>
    </>
  );
}

export function RallyLengthPanel({ bands, rallies, playerName, className }: RallyLengthPanelProps) {
  return (
    <Panel
      title="Rallies won by length"
      subtitle={`${rallies.toLocaleString("en-US")} rallies`}
      className={className}
    >
      <div className="grid gap-8">
        {bands.map((b) => (
          <div key={b.band}>
            <div className="mb-2 flex items-baseline justify-between gap-4">
              <span className="font-medium">{b.label}</span>
              <span className="text-sm tabular-nums text-muted-foreground">
                {b.rallies.toLocaleString("en-US")} rallies
              </span>
            </div>
            <div className="grid grid-cols-[auto_minmax(48px,1fr)_40px] items-center gap-x-4 gap-y-1.5 text-sm">
              <Label text={playerName} />
              {b.winRate === null ? (
                <span className="col-span-2 text-muted-foreground">Too few to compare</span>
              ) : (
                <Bar value={b.winRate} />
              )}
              <Label text="Typical pro" />
              <Bar value={b.typical} typical />
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
