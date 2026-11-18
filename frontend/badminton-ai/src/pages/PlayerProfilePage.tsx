import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ProShell } from "@/features/pros/components/ProShell";
import { ProfileHeader } from "@/features/pros/components/ProfileHeader";
import { FindingsPanel, RallyListPanel } from "@/features/pros/components/FindingsPanel";
import { WatchPanel } from "@/features/pros/components/WatchPanel";
import { RallyLengthPanel } from "@/features/pros/components/RallyLengthPanel";
import { ShotChoicePanel } from "@/features/pros/components/ShotChoicePanel";
import { useProData } from "@/features/pros/hooks/useProData";
import { fetchPlayer } from "@/features/pros/proData";
import type { PlayerProfile, View } from "@/features/pros/types";

const span = {
  findings: "col-span-4 max-[1180px]:col-span-6 max-[760px]:col-span-12",
  watch: "col-span-5 max-[1180px]:-order-1 max-[1180px]:col-span-12",
  length: "col-span-3 max-[1180px]:col-span-6 max-[760px]:col-span-12",
  shots: "col-span-12",
};

function pronouns(player: PlayerProfile) {
  return player.event === "WS" ? { he: "she", his: "her" } : { he: "he", his: "his" };
}

function AllMatchesBody({ view }: { view: View }) {
  const [selected, setSelected] = useState(0);
  const [clipIndex, setClipIndex] = useState(0);
  const finding = view.findings[selected];

  const select = (i: number) => {
    setSelected(i);
    setClipIndex(0);
  };

  const clips = finding ? finding.clips : view.rallyBrowser.slice(0, 1);

  return (
    <>
      <FindingsPanel
        findings={view.findings}
        selected={selected}
        onSelect={select}
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

function FilteredBody({ view }: { view: View }) {
  const [clipIndex, setClipIndex] = useState(0);
  const clips = view.rallyBrowser;

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

function Profile({ player }: { player: PlayerProfile }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("view") ?? "all";
  const viewId = player.views[requested] ? requested : "all";
  const view = player.views[viewId];
  const filtered = viewId !== "all";
  const pronoun = pronouns(player);

  const changeView = (id: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id === "all") next.delete("view");
        else next.set("view", id);
        return next;
      },
      { replace: true },
    );
  };

  return (
    <>
      <title>{`${player.name} | Shuttleye`}</title>
      <ProfileHeader player={player} viewId={viewId} onViewChange={changeView} />
      {view && (
        <div key={viewId} className="grid grid-cols-12 gap-6 max-[900px]:gap-4">
          {filtered ? (
            <FilteredBody view={view} />
          ) : (
            <AllMatchesBody view={view} />
          )}
          <RallyLengthPanel
            bands={view.bands}
            rallies={view.rallies}
            playerName={player.name}
            className={span.length}
          />
          <ShotChoicePanel
            rows={view.shotChoice}
            shots={view.shots}
            ranked={!filtered}
            pronoun={pronoun}
            className={span.shots}
          />
        </div>
      )}
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
        to="/players"
        className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        See all players
      </Link>
    </div>
  );
}

function PlayerProfileLoader({ playerId }: { playerId: string }) {
  const state = useProData(() => fetchPlayer(playerId), [playerId]);

  if (state.status === "loading") {
    return <p className="py-16 text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.status === "error") {
    if (state.error.kind === "not-found") return <NotFound />;
    return (
      <p className="py-16 text-muted-foreground">
        Couldn't load this profile. {state.error.message}
      </p>
    );
  }
  if (state.data.id !== playerId) return <NotFound />;
  return <Profile player={state.data} />;
}

export default function PlayerProfilePage() {
  const { playerId = "" } = useParams();
  return (
    <ProShell>
      <PlayerProfileLoader key={playerId} playerId={playerId} />
    </ProShell>
  );
}
