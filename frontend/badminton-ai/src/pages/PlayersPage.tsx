import { useId, useMemo, useState } from "react";
import { ProShell } from "@/features/pros/components/ProShell";
import { PlayerCard } from "@/features/pros/components/PlayerCard";
import { useProData } from "@/features/pros/hooks/useProData";
import { fetchPlayerIndex } from "@/features/pros/proData";
import { matchCount, normalizeName } from "@/features/pros/search";
import type { PlayerIndexEntry, ProEvent } from "@/features/pros/types";

const sections: { event: ProEvent; title: string }[] = [
  { event: "MS", title: "Men's singles" },
  { event: "WS", title: "Women's singles" },
];

function PlayerList({ players }: { players: PlayerIndexEntry[] }) {
  const [query, setQuery] = useState("");
  const inputId = useId();
  const q = normalizeName(query.trim());
  const shown = useMemo(
    () => (q ? players.filter((p) => normalizeName(p.name).includes(q)) : players),
    [players, q],
  );

  return (
    <>
      <div className="mt-6">
        <label htmlFor={inputId} className="block text-sm font-medium">
          Search players
        </label>
        <input
          id={inputId}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="mt-2 min-h-11 w-full max-w-md rounded-lg border border-foreground/30 bg-card px-3 text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        />
      </div>
      <p role="status" className={shown.length === 0 ? "mt-8 text-muted-foreground" : "sr-only"}>
        {shown.length === 0
          ? `No players match "${query.trim()}".`
          : q
            ? `${shown.length} ${shown.length === 1 ? "player" : "players"} found`
            : ""}
      </p>
      {sections.map(({ event, title }) => {
        const group = shown.filter((p) => p.event === event);
        if (group.length === 0) return null;
        return (
          <section key={event} aria-labelledby={`${inputId}-${event}`} className="mt-8">
            <h2 id={`${inputId}-${event}`} className="text-[18px] font-semibold">
              {title}
            </h2>
            <ul className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
              {group.map((p) => (
                <li key={p.id}>
                  <PlayerCard
                    to={`/players/${encodeURIComponent(p.id)}`}
                    name={p.name}
                    photo={p.photo}
                    detail={p.ranked ? matchCount(p.matches) : "Not enough data to rank"}
                    muted={!p.ranked}
                  />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}

function Body() {
  const state = useProData(fetchPlayerIndex, []);
  if (state.status === "loading") {
    return <p className="py-8 text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.status === "error") {
    return <p className="py-8 text-muted-foreground">Couldn't load players.</p>;
  }
  return <PlayerList players={state.data.players} />;
}

export default function PlayersPage() {
  return (
    <ProShell>
      <title>Pro players | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Pro players</h1>
      <p className="mt-2 text-muted-foreground">
        Singles players from BWF World Tour matches, 2018 to 2022.
      </p>
      <Body />
    </ProShell>
  );
}
