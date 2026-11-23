import { useId, useMemo, useState } from "react";
import { ProShell } from "@/features/pros/components/ProShell";
import { PairCard } from "@/features/pros/components/PairCard";
import { useProData } from "@/features/pros/hooks/useProData";
import { eventLabels } from "@/features/pros/pairFormat";
import { fetchPairIndex } from "@/features/pros/proData";
import { normalizeName } from "@/features/pros/search";
import type { PairEvent, PairIndexEntry } from "@/features/pros/types";

const events: PairEvent[] = ["MD", "WD", "XD"];

function PairList({ pairs }: { pairs: PairIndexEntry[] }) {
  const [query, setQuery] = useState("");
  const inputId = useId();
  const q = normalizeName(query.trim());
  const shown = useMemo(
    () =>
      q ? pairs.filter((p) => p.players.some((pl) => normalizeName(pl.name).includes(q))) : pairs,
    [pairs, q],
  );

  return (
    <>
      <div className="mt-6">
        <label htmlFor={inputId} className="block text-sm font-medium">
          Search pairs
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
          ? `No pairs match "${query.trim()}".`
          : q
            ? `${shown.length} ${shown.length === 1 ? "pair" : "pairs"} found`
            : ""}
      </p>
      {events.map((event) => {
        const group = shown.filter((p) => p.event === event);
        if (group.length === 0) return null;
        return (
          <section key={event} aria-labelledby={`${inputId}-${event}`} className="mt-8">
            <h2 id={`${inputId}-${event}`} className="text-[18px] font-semibold">
              {eventLabels[event]}
            </h2>
            <ul className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4 max-[360px]:grid-cols-1">
              {group.map((p) => (
                <li key={p.id}>
                  <PairCard pair={p} />
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
  const state = useProData(fetchPairIndex, []);
  if (state.status === "loading") {
    return <p className="py-8 text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.status === "error") {
    return <p className="py-8 text-muted-foreground">Couldn't load pairs.</p>;
  }
  return <PairList pairs={state.data.pairs} />;
}

export default function PairsPage() {
  return (
    <ProShell source="doubles">
      <title>Doubles pairs | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Doubles pairs</h1>
      <p className="mt-2 text-muted-foreground">
        Doubles pairs from BWF World Tour matches, 2022 to 2025.
      </p>
      <Body />
    </ProShell>
  );
}
