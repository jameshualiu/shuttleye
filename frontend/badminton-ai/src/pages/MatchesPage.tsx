import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MatchRow } from "@/features/library/components/MatchRow";
import { useIsAdmin } from "@/features/library/hooks/useIsAdmin";
import { useLibraryDoc } from "@/features/library/hooks/useLibraryDoc";
import { useLibraryIndex } from "@/features/library/hooks/useLibraryIndex";
import { fetchUnpublishedMatches } from "@/features/library/libraryData";
import { ok } from "@/lib/result";
import type { LibraryIndex, UnpublishedMatch } from "@/features/library/types";
import { cn } from "@/lib/utils";

const field =
  "min-h-11 rounded-full border border-border bg-card px-4 text-[15px] text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

const fold = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

function Unpublished({ fixture, editions }: { fixture: boolean; editions: Map<string, string> }) {
  const state = useLibraryDoc(() => {
    if (import.meta.env.DEV && fixture) {
      return import("@/features/library/__fixtures__/library.json").then((m) =>
        ok(m.default.unpublished as unknown as UnpublishedMatch[]),
      );
    }
    return fetchUnpublishedMatches();
  }, [fixture]);

  if (state.status !== "ready" || state.data.length === 0) return null;
  const rows = [...state.data].sort((a, b) => b.date.localeCompare(a.date));
  return (
    <section aria-labelledby="unpublished-h" className="mt-10">
      <h2 id="unpublished-h" className="text-[18px] font-semibold">
        Unpublished
      </h2>
      <p className="mt-0.5 text-sm text-muted-foreground">Only admins see these.</p>
      <ul className="mt-3 divide-y divide-border rounded-2xl bg-card p-2">
        {rows.map((m) => (
          <li key={m.id}>
            <MatchRow
              match={m}
              editionLabel={editions.get(m.editionId)}
              year={m.date.slice(0, 4)}
              note={m.warnings > 0 ? `${m.warnings} ${m.warnings === 1 ? "warning" : "warnings"}` : undefined}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function Library({ index, fixture }: { index: LibraryIndex; fixture: boolean }) {
  const signedInAdmin = useIsAdmin();
  const admin = signedInAdmin || (import.meta.env.DEV && fixture); // DEV fixture shows the section
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const tournament = params.get("tournament") ?? "";
  const year = params.get("year") ?? "";

  const setParam = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  const editions = useMemo(() => new Map(index.editions.map((e) => [e.id, e])), [index]);
  const editionNames = useMemo(
    () => new Map(index.editions.map((e) => [e.id, e.name])),
    [index],
  );
  const yearOf = (m: { editionId: string; date: string }) =>
    String(editions.get(m.editionId)?.season ?? m.date.slice(0, 4));

  const tournamentOptions = useMemo(() => {
    const used = index.editions.filter((e) => index.matches.some((m) => m.editionId === e.id));
    // Names repeat across seasons: add the season only where a name would be ambiguous.
    return used
      .map((e) => ({
        id: e.id,
        label: used.filter((o) => o.name === e.name).length > 1 ? `${e.name} ${e.season}` : e.name,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [index]);

  const years = useMemo(
    () => [...new Set(index.matches.map(yearOf))].sort((a, b) => b.localeCompare(a)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [index, editions],
  );

  const q = fold(query.trim());
  const rows = index.matches
    .filter(
      (m) =>
        (!tournament || m.editionId === tournament) &&
        (!year || yearOf(m) === year) &&
        (!q || fold(m.players.A.name).includes(q) || fold(m.players.B.name).includes(q)),
    )
    .sort((a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id));

  return (
    <>
      <h1 className="text-[32px] font-semibold tracking-tight">Matches</h1>
      <p className="mt-1 text-muted-foreground">
        {index.matches.length} analysed BWF singles {index.matches.length === 1 ? "match" : "matches"}.
      </p>

      <form role="search" onSubmit={(e) => e.preventDefault()} className="mt-6 flex flex-wrap gap-3">
        <label className="min-w-[220px] flex-1">
          <span className="sr-only">Search by player name</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by player"
            className={cn(field, "w-full")}
          />
        </label>
        <label>
          <span className="sr-only">Tournament</span>
          <select
            value={tournament}
            onChange={(e) => setParam("tournament", e.target.value)}
            className={cn(field, "max-w-[280px] cursor-pointer max-[600px]:max-w-full")}
          >
            <option value="">All tournaments</option>
            {tournamentOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Year</span>
          <select
            value={year}
            onChange={(e) => setParam("year", e.target.value)}
            className={cn(field, "cursor-pointer")}
          >
            <option value="">All years</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </form>

      <section aria-label="Matches" className="mt-6">
        {rows.length === 0 ? (
          <p className="rounded-2xl bg-card p-6 text-muted-foreground">
            {index.matches.length === 0 ? "No matches in the library yet." : "No matches fit these filters."}
          </p>
        ) : (
          <>
            <p aria-live="polite" className="mb-2 px-1 text-sm text-muted-foreground">
              {rows.length} {rows.length === 1 ? "match" : "matches"}
            </p>
            <ul className="divide-y divide-border rounded-2xl bg-card p-2">
              {rows.map((m) => (
                <li key={m.id}>
                  <MatchRow match={m} editionLabel={editionNames.get(m.editionId)} year={yearOf(m)} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {admin && <Unpublished fixture={fixture} editions={editionNames} />}
    </>
  );
}

export default function MatchesPage() {
  const [params] = useSearchParams();
  const fixture = params.has("fixture");
  const state = useLibraryIndex(fixture);

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-8 min-[760px]:px-12">
      <title>Matches | Shuttleye</title>
      <main>
        {state.status === "loading" && <p className="text-muted-foreground">Loading matches…</p>}
        {state.status === "error" && (
          <p className="text-muted-foreground">
            {state.error.kind === "network"
              ? `Couldn't load the matches: ${state.error.message}`
              : "The match library isn't available yet."}
          </p>
        )}
        {state.status === "ready" && <Library index={state.data} fixture={fixture} />}
      </main>
    </div>
  );
}
