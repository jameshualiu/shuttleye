import { ChevronDown } from "lucide-react";
import type { PlayerFilter, PlayerProfile } from "../types";
import { cn } from "@/lib/utils";
import { PlayerPhoto } from "./PlayerPhoto";

type ProfileHeaderProps = {
  player: PlayerProfile;
  viewId: string;
  onViewChange: (viewId: string) => void;
};

const groups: { kind: PlayerFilter["kind"]; label: string }[] = [
  { kind: "tournament", label: "Tournaments" },
  { kind: "match", label: "Matches" },
];

export function ProfileHeader({ player, viewId, onViewChange }: ProfileHeaderProps) {
  const { context } = player;
  const filtered = viewId !== "all";
  const eventLabel = player.event === "WS" ? "Women's" : "Men's";
  const allFilters = player.filters.filter((f) => f.kind === "all");

  return (
    <header className="flex items-start justify-between gap-8 pb-8 max-[900px]:flex-col max-[900px]:gap-4">
      <div className="flex min-w-0 flex-1 items-start gap-8 max-[900px]:gap-4">
        <PlayerPhoto
          photo={player.photo}
          name={player.name}
          size={132}
          className="rounded-[20px] max-[900px]:hidden"
        />
        <PlayerPhoto
          photo={player.photo}
          name={player.name}
          size={88}
          className="min-[901px]:hidden"
        />
        <div className="min-w-0">
          <h1 className="text-[56px] font-semibold leading-none tracking-[-0.04em] max-[900px]:text-[44px]">
            {player.name}
          </h1>
          <p className="mt-2 text-muted-foreground">
            {eventLabel} singles. {context.matches} {context.matches === 1 ? "match" : "matches"} from {context.firstYear} to{" "}
            {context.lastYear}, compared with {context.comparedWith} other pros.
          </p>
          {!filtered && player.summary && (
            <p className="mt-4 max-w-[68ch] text-[19px] leading-normal text-foreground">
              {player.summary}
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-2 max-[900px]:items-start">
        <label htmlFor="match-filter" className="sr-only">
          Matches
        </label>
        <div className="relative">
          <select
            id="match-filter"
            value={viewId}
            onChange={(e) => onViewChange(e.target.value)}
            className={cn(
              "min-h-11 max-w-[320px] cursor-pointer appearance-none truncate rounded-full border border-border bg-card py-2.5 pl-4 pr-10 text-[15px] text-foreground",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
            )}
          >
            {allFilters.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
            {groups.map((g) => {
              const items = player.filters.filter((f) => f.kind === g.kind);
              if (items.length === 0) return null;
              return (
                <optgroup key={g.kind} label={g.label}>
                  {items.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.label}
                    </option>
                  ))}
                </optgroup>
              );
            })}
          </select>
          <ChevronDown
            aria-hidden="true"
            className="pointer-events-none absolute right-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
        </div>
        {filtered && (
          <p className="text-sm text-muted-foreground">Rankings and findings use all matches.</p>
        )}
      </div>
    </header>
  );
}
