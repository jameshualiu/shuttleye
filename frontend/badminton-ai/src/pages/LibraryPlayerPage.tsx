import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { FindingsPanel, RallyListPanel } from "@/features/pros/components/FindingsPanel";
import { MatchFilter } from "@/features/pros/components/ProfileHeader";
import { PlayerPhoto } from "@/features/pros/components/PlayerPhoto";
import { Panel } from "@/features/pros/components/Panel";
import { WatchPanel } from "@/features/pros/components/WatchPanel";
import { InsightCards } from "@/features/library/components/InsightCards";
import { MatchRow } from "@/features/library/components/MatchRow";
import { useLibraryDoc } from "@/features/library/hooks/useLibraryDoc";
import { useLibraryIndex } from "@/features/library/hooks/useLibraryIndex";
import { fetchLibraryPlayer, fetchLibraryView } from "@/features/library/libraryData";
import type { LibraryIndex, LibraryPlayer, LibraryView } from "@/features/library/types";
import { ok } from "@/lib/result";

const COMPARED_NOTE = "Comparisons with other pros appear once 10 players have enough matches.";

function contextLine(player: LibraryPlayer): string {
  const { matches, firstYear, lastYear, comparedWith } = player.context;
  const count = `${matches} ${matches === 1 ? "match" : "matches"}`;
  const span = firstYear === lastYear ? `in ${firstYear}` : `from ${firstYear} to ${lastYear}`;
  const tail = comparedWith > 0 ? `, compared with ${comparedWith} other pros` : "";
  return `${count} ${span}${tail}.`;
}

function Header({
  player,
  viewId,
  onViewChange,
}: {
  player: LibraryPlayer;
  viewId: string;
  onViewChange: (id: string) => void;
}) {
  const eventLabel = player.event === "WS" ? "Women's" : "Men's";
  return (
    <header className="flex items-start justify-between gap-8 pb-8 max-[900px]:flex-col max-[900px]:gap-4">
      <div className="flex min-w-0 flex-1 items-start gap-8 max-[900px]:gap-4">
        <PlayerPhoto photo={player.photo} name={player.name} size={132} radius={20} className="max-[900px]:hidden" />
        <PlayerPhoto photo={player.photo} name={player.name} size={88} radius={16} className="min-[900px]:hidden" />
        <div className="min-w-0">
          <h1 className="text-[56px] font-semibold leading-none tracking-[-0.04em] max-[900px]:text-[44px]">
            {player.name}
          </h1>
          <p className="mt-2 text-muted-foreground">
            {eventLabel} singles. {contextLine(player)}
          </p>
          {player.context.comparedWith === 0 && (
            <p className="mt-1 text-sm text-muted-foreground">{COMPARED_NOTE}</p>
          )}
          {viewId === "all" && player.summary && (
            <p className="mt-4 max-w-[68ch] text-[19px] leading-normal text-foreground">{player.summary}</p>
          )}
        </div>
      </div>
      <MatchFilter filters={player.filters} viewId={viewId} onViewChange={onViewChange} />
    </header>
  );
}

const span = {
  findings: "col-span-5 self-start max-[1180px]:col-span-12",
  watch: "col-span-7 max-[1180px]:col-span-12",
};

function Clips({ view, ranked }: { view: LibraryView; ranked: boolean }) {
  const filtered = view.kind !== "all";
  const [selected, setSelected] = useState(0);
  const [clipIndex, setClipIndex] = useState(0);
  const finding = filtered ? undefined : view.findings[selected];
  // No findings: the build supplies up to 5 example rallies (all view), or the selection's rallies.
  const clips = finding ? finding.clips : view.rallyBrowser;

  if (filtered) {
    return (
      <>
        <RallyListPanel
          clips={clips}
          rallies={view.rallies}
          selected={clipIndex}
          onSelect={setClipIndex}
          className={span.findings}
        />
        <WatchPanel
          title="Watch a rally"
          clips={clips}
          index={clipIndex}
          onIndexChange={setClipIndex}
          className={span.watch}
        />
      </>
    );
  }
  return (
    <>
      <FindingsPanel
        findings={view.findings}
        ranked={ranked}
        selected={selected}
        onSelect={(i) => {
          setSelected(i);
          setClipIndex(0);
        }}
        className={span.findings}
      />
      <WatchPanel
        title={finding ? finding.claim : "Example rallies"}
        subtitle={
          clips.length > 0
            ? `${clips.length} example ${clips.length === 1 ? "rally" : "rallies"}`
            : undefined
        }
        clips={clips}
        index={clipIndex}
        onIndexChange={setClipIndex}
        tip={finding?.tip}
        className={span.watch}
      />
    </>
  );
}

function PlayerMatches({ playerId, index }: { playerId: string; index: LibraryIndex | null }) {
  const rows = useMemo(
    () =>
      (index?.matches ?? [])
        .filter((m) => m.players.A.id === playerId || m.players.B.id === playerId)
        .sort((a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id)),
    [index, playerId],
  );
  if (!index || rows.length === 0) return null;
  const editions = new Map(index.editions.map((e) => [e.id, e]));
  return (
    <Panel title="Matches" subtitle="Open one to watch it with the shot-by-shot breakdown" className="col-span-12">
      <ul className="-mx-2 divide-y divide-border">
        {rows.map((m) => (
          <li key={m.id}>
            <MatchRow
              match={m}
              editionLabel={editions.get(m.editionId)?.name}
              year={editions.get(m.editionId)?.season ?? m.date.slice(0, 4)}
              note={m.players.A.id === playerId ? "won" : "lost"}
            />
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function ViewBody({
  player,
  viewId,
  index,
  fixture,
}: {
  player: LibraryPlayer;
  viewId: string;
  index: LibraryIndex | null;
  fixture: boolean;
}) {
  const state = useLibraryDoc(() => {
    if (import.meta.env.DEV && fixture) {
      return import("@/features/library/__fixtures__/library.json").then((m) =>
        ok(m.default.view as unknown as LibraryView),
      );
    }
    return fetchLibraryView(player.id, viewId);
  }, [player.id, viewId, fixture]);
  const ranked = index?.players.find((p) => p.id === player.id)?.ranked ?? player.context.comparedWith > 0;

  if (state.status === "loading") return <p className="text-muted-foreground">Loading…</p>;
  if (state.status === "error") {
    return <p className="text-muted-foreground">Couldn't load this selection.</p>;
  }
  const view = state.data;
  return (
    <div className="grid grid-cols-12 gap-6 max-[900px]:gap-4">
      <section aria-labelledby="style-h" className="col-span-12">
        <h2 id="style-h" className="text-[18px] font-semibold">
          How {player.name} plays
        </h2>
        <p className="mb-4 mt-1 text-[14px] text-muted-foreground">
          {view.shots.toLocaleString("en-US")} shots in {view.rallies.toLocaleString("en-US")} rallies
        </p>
        <InsightCards insights={view.insights} />
      </section>
      <Clips key={viewId} view={view} ranked={ranked} />
      <PlayerMatches playerId={player.id} index={index} />
    </div>
  );
}

function Profile({ player, index, fixture }: { player: LibraryPlayer; index: LibraryIndex | null; fixture: boolean }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("view") ?? "all";
  const viewId = player.filters.some((f) => f.id === requested) ? requested : "all";

  const changeView = (id: string) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id === "all") next.delete("view");
        else next.set("view", id);
        return next;
      },
      { replace: true },
    );

  return (
    <>
      <title>{`${player.name} | Shuttleye`}</title>
      <Header player={player} viewId={viewId} onViewChange={changeView} />
      <ViewBody player={player} viewId={viewId} index={index} fixture={fixture} />
    </>
  );
}

function NotFound() {
  return (
    <div className="py-16">
      <title>Player not found | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Not found</h1>
      <p className="mt-2 text-muted-foreground">We don't have a profile for this player.</p>
      <Link
        to="/matches"
        className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        See all matches
      </Link>
    </div>
  );
}

export default function LibraryPlayerPage() {
  const { playerId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const fixture = searchParams.has("fixture");
  const player = useLibraryDoc(() => {
    if (import.meta.env.DEV && fixture) {
      return import("@/features/library/__fixtures__/library.json").then((m) =>
        ok(m.default.player as unknown as LibraryPlayer),
      );
    }
    return fetchLibraryPlayer(playerId);
  }, [playerId, fixture]);
  const index = useLibraryIndex(fixture);

  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-8 min-[760px]:px-12">
      <main>
        {player.status === "loading" && <p className="py-16 text-sm text-muted-foreground">Loading…</p>}
        {player.status === "error" &&
          (player.error.kind === "network" ? (
            <p className="py-16 text-muted-foreground">Couldn't load this profile. {player.error.message}</p>
          ) : (
            <NotFound />
          ))}
        {player.status === "ready" && (
          <Profile
            key={player.data.id}
            player={player.data}
            index={index.status === "ready" ? index.data : null}
            fixture={fixture}
          />
        )}
      </main>
    </div>
  );
}
