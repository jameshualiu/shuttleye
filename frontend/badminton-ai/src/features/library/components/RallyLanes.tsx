import { cn } from "@/lib/utils";
import { scoreText } from "../names";
import type { LibraryPlayerRef, RallyDoc, ShotDoc, Side } from "../types";
import { LEGEND_GROUPS, shotFill, shotInk, shotLabel } from "./shotColors";

// Shots sit between these percentages of the track so edge chips aren't clipped.
const PAD = 4;
const CHIP_PX = 64;

type Lane = { key: string; name: string; shots: { shot: ShotDoc; index: number }[] };

function position(t: number, rally: RallyDoc): number {
  const span = rally.endSec - rally.startSec;
  const frac = span > 0 ? (t - rally.startSec) / span : 0.5;
  return PAD + Math.min(1, Math.max(0, frac)) * (100 - 2 * PAD);
}

type RallyLanesProps = {
  rally: RallyDoc;
  players: Record<Side, LibraryPlayerRef>;
  onSeek: (sec: number) => void;
  className?: string;
};

export function RallyLanes({ rally, players, onSeek, className }: RallyLanesProps) {
  const lanes: Lane[] = (["A", "B"] as const).map((side) => ({
    key: side,
    name: players[side].name,
    shots: [],
  }));
  const unknown: Lane = { key: "unknown", name: "Unknown", shots: [] };
  rally.shots.forEach((shot, index) => {
    const lane = shot.p === "A" ? lanes[0] : shot.p === "B" ? lanes[1] : unknown;
    lane.shots.push({ shot, index });
  });
  if (unknown.shots.length > 0) lanes.push(unknown);

  const seconds = Math.max(0, rally.endSec - rally.startSec);
  const trackMin = Math.max(560, rally.shots.length * CHIP_PX);
  const ticks = [0, seconds / 2, seconds];

  return (
    <section aria-labelledby={`rally-${rally.n}`} className={className}>
      <div className="mb-3 mt-6 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={`rally-${rally.n}`} className="text-[16px] font-semibold tabular-nums">
          Rally {rally.n} · {scoreText(rally.scoreBefore)} · {rally.shots.length}{" "}
          {rally.shots.length === 1 ? "shot" : "shots"} · {seconds.toFixed(1)} s
        </h2>
        <p className="text-sm text-muted-foreground">Click a shot to jump the video to it</p>
      </div>
      <div className="rounded-2xl bg-card text-card-foreground">
        <div className="overflow-x-auto px-4 pb-2 pt-4">
          {lanes.map((lane) => (
            <div key={lane.key} className="grid grid-cols-[88px_1fr] items-center">
              <div className="sticky left-0 z-10 truncate bg-card pr-2 text-[13px] text-muted-foreground">
                {lane.name}
              </div>
              <div className="relative h-10" style={{ minWidth: trackMin }}>
                <div aria-hidden="true" className="absolute inset-x-0 top-1/2 border-t border-dashed border-border" />
                {lane.shots.map(({ shot, index }) => {
                  const label = shotLabel(shot);
                  return (
                    <button
                      key={index}
                      type="button"
                      onClick={() => onSeek(shot.t)}
                      aria-label={`Shot ${index + 1}: ${lane.name} ${label.toLowerCase()} at ${(
                        shot.t - rally.startSec
                      ).toFixed(1)} s`}
                      className={cn(
                        "absolute top-1.5 -translate-x-1/2 cursor-pointer whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold",
                        "hover:outline-2 hover:outline-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                      )}
                      style={{
                        left: `${position(shot.t, rally)}%`,
                        background: shotFill(label),
                        color: shotInk(label),
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <div className="grid grid-cols-[88px_1fr]">
            <div className="sticky left-0 bg-card" />
            <div className="relative h-5 text-[11px] text-muted-foreground tabular-nums" style={{ minWidth: trackMin }}>
              {ticks.map((s, i) => (
                <span
                  key={i}
                  className="absolute -translate-x-1/2"
                  style={{ left: `${PAD + (i / 2) * (100 - 2 * PAD)}%` }}
                >
                  {s === 0 ? "0" : s.toFixed(1)} s
                </span>
              ))}
            </div>
          </div>
        </div>
        <p className="px-4 pb-3 text-sm">
          {rally.winner ? (
            <>
              <span className="font-medium">{players[rally.winner].name}</span> won the rally
            </>
          ) : (
            <span className="text-muted-foreground">Score not read</span>
          )}
        </p>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 px-4 pb-4 text-xs text-muted-foreground" aria-label="Shot colours">
          {LEGEND_GROUPS.map((g) => (
            <li key={g} className="inline-flex items-center gap-1.5">
              <i aria-hidden="true" className="inline-block size-2.5 rounded-[3px]" style={{ background: shotFill(g) }} />
              {g}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
