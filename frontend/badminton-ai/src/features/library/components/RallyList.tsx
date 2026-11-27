import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { scoreText } from "../names";
import type { LibraryPlayerRef, RallyDoc, Side } from "../types";

/** The pro_profiles "long" band: 9 shots or more. */
export const LONG_RALLY_SHOTS = 9;

const focus = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

const chip = cn(
  "inline-flex min-h-8 cursor-pointer items-center rounded-full border border-border px-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground aria-pressed:border-foreground aria-pressed:bg-foreground aria-pressed:text-background",
  focus,
);

export function WinnerDot({ side }: { side: Side | null }) {
  if (side === "A") return <i aria-hidden="true" className="inline-block size-2 rounded-full bg-foreground" />;
  if (side === "B")
    return (
      <i aria-hidden="true" className="inline-block size-2 rounded-full border-[1.5px] border-muted-foreground" />
    );
  return <i aria-hidden="true" className="inline-block h-px w-2 bg-muted-foreground" />;
}

type RallyListProps = {
  rallies: RallyDoc[];
  players: Record<Side, LibraryPlayerRef>;
  selected: number | null;
  onSelect: (rally: RallyDoc) => void;
  className?: string;
};

export function RallyList({ rallies, players, selected, onSelect, className }: RallyListProps) {
  const [longOnly, setLongOnly] = useState(false);
  const [lostBy, setLostBy] = useState<Side | null>(null);
  const [game, setGame] = useState<number | null>(null);

  const games = useMemo(
    () => [...new Set(rallies.flatMap((r) => (r.set === null ? [] : [r.set])))].sort((a, b) => a - b),
    [rallies],
  );
  const maxShots = useMemo(() => Math.max(1, ...rallies.map((r) => r.shots.length)), [rallies]);
  const shown = rallies.filter(
    (r) =>
      (!longOnly || r.shots.length >= LONG_RALLY_SHOTS) &&
      // "Lost points" for a player: rallies the other player won (unread winners excluded).
      (lostBy === null || (r.winner !== null && r.winner !== lostBy)) &&
      (game === null || r.set === game),
  );
  const a = players.A.name;
  const b = players.B.name;

  // Keep the selected rally in view as the video moves on. Scrolls the list only,
  // never the page.
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>('[aria-pressed="true"]');
    if (!list || !item) return;
    const top = item.offsetTop; // the list is the offset parent (relative)
    if (top < list.scrollTop) list.scrollTop = top;
    else if (top + item.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = top + item.offsetHeight - list.clientHeight;
  }, [selected]);

  return (
    <section aria-label="Rallies" className={cn("flex flex-col rounded-2xl bg-card text-card-foreground", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-3">
        <h2 className="text-[15px] font-semibold">Rallies</h2>
        <span className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <WinnerDot side="A" /> {a} won
          </span>
          <span className="inline-flex items-center gap-1.5">
            <WinnerDot side="B" /> {b} won
          </span>
        </span>
      </div>

      <div className="grid gap-2 border-b border-border px-4 py-3" role="group" aria-label="Filter rallies">
        <div className="flex flex-wrap gap-2">
          <button type="button" aria-pressed={longOnly} onClick={() => setLongOnly((v) => !v)} className={chip}>
            Long rallies ({LONG_RALLY_SHOTS}+)
          </button>
          {games.length > 1 &&
            games.map((g) => (
              <button
                key={g}
                type="button"
                aria-pressed={game === g}
                onClick={() => setGame(game === g ? null : g)}
                className={chip}
              >
                Game {g}
              </button>
            ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Lost points:</span>
          {(["A", "B"] as const).map((side) => (
            <button
              key={side}
              type="button"
              aria-pressed={lostBy === side}
              onClick={() => setLostBy(lostBy === side ? null : side)}
              className={chip}
            >
              {side === "A" ? a : b}
            </button>
          ))}
        </div>
      </div>

      <p className="px-4 pt-2 text-xs text-muted-foreground" aria-live="polite">
        {shown.length === rallies.length
          ? `${rallies.length} rallies`
          : `${shown.length} of ${rallies.length} rallies`}
      </p>
      {shown.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">No rallies match these filters.</p>
      ) : (
        <ul ref={listRef} className="relative max-h-[520px] overflow-y-auto py-1 max-[899px]:max-h-[420px]">
          {shown.map((r) => (
            <li key={r.n}>
              <button
                type="button"
                aria-pressed={r.n === selected}
                aria-label={`Rally ${r.n}, score ${scoreText(r.scoreBefore)}, ${
                  r.winner ? `${players[r.winner].name} won` : "winner not read"
                }, ${r.shots.length} shots`}
                onClick={() => onSelect(r)}
                className={cn(
                  "grid min-h-10 w-full cursor-pointer grid-cols-[32px_64px_1fr_60px] items-center gap-2 px-4 py-2 text-left text-[13px] tabular-nums transition-colors hover:bg-muted/60 aria-pressed:bg-muted aria-pressed:shadow-[inset_3px_0_0_var(--foreground)]",
                  focus,
                )}
              >
                <span className="text-muted-foreground">{r.n}</span>
                <span className="flex items-center gap-1.5">
                  <WinnerDot side={r.winner} />
                  {scoreText(r.scoreBefore)}
                </span>
                <span className="h-1 overflow-hidden rounded-full bg-muted-foreground/15">
                  <span
                    className="block h-full rounded-full bg-muted-foreground"
                    style={{ width: `${(r.shots.length / maxShots) * 100}%` }}
                  />
                </span>
                <span className="text-right text-muted-foreground">
                  {r.shots.length} {r.shots.length === 1 ? "shot" : "shots"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
