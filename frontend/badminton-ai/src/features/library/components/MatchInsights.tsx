import { useState } from "react";
import { Play } from "lucide-react";
import { KindBadge } from "@/features/pros/components/FindingsPanel";
import { cn } from "@/lib/utils";
import type { LibraryPlayerRef, MatchInsights as MatchInsightsData, Side } from "../types";
import { InsightCards } from "./InsightCards";

const focus = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

const toggle = cn(
  "min-h-9 cursor-pointer rounded-full px-4 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground aria-pressed:bg-foreground aria-pressed:text-background",
  focus,
);

type MatchInsightsProps = {
  insights: MatchInsightsData | null;
  players: Record<Side, LibraryPlayerRef>;
  onSeek: (sec: number) => void;
};

export function MatchInsights({ insights, players, onSeek }: MatchInsightsProps) {
  const [side, setSide] = useState<Side>("A");
  const player = players[side];
  const data = insights?.[side];

  return (
    <section aria-labelledby="match-insights" className="mt-10">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="match-insights" className="text-[18px] font-semibold">
            How this match was won
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Each finding compares this match with the player's other matches
          </p>
        </div>
        {insights && (
          <div role="group" aria-label="Player" className="inline-flex gap-1 rounded-full bg-card p-1">
            {(["A", "B"] as const).map((s) => (
              <button key={s} type="button" aria-pressed={side === s} onClick={() => setSide(s)} className={toggle}>
                {players[s].name}
              </button>
            ))}
          </div>
        )}
      </div>

      {!data ? (
        <p className="rounded-2xl bg-card p-5 text-muted-foreground">
          Insights appear once the match is published.
        </p>
      ) : (
        <>
          <div className="mb-4 rounded-2xl bg-card p-5">
            {data.findings.length === 0 ? (
              <p className="text-muted-foreground">
                Nothing to compare: this is our only match of {player.name}, or nothing stood out
                from their other matches.
              </p>
            ) : (
              <ul className="grid gap-4">
                {data.findings.map((f) => (
                  <li key={f.key}>
                    <p className="font-medium">
                      <KindBadge kind={f.kind} />
                      {f.claim}
                    </p>
                    {f.clips.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {f.clips.map((c, i) => (
                          <button
                            key={`${c.startSec}-${i}`}
                            type="button"
                            onClick={() => onSeek(c.startSec)}
                            className={cn(
                              "inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-full border border-border px-3 text-xs text-foreground transition-colors hover:bg-muted",
                              focus,
                            )}
                          >
                            <Play aria-hidden="true" className="size-3" />
                            <span className="first-letter:uppercase">{c.scoreLabel}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <InsightCards key={side} insights={data.insights} />
        </>
      )}
    </section>
  );
}
