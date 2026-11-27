import { useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { ok } from "@/lib/result";
import { MatchHeader } from "@/features/library/components/MatchHeader";
import { MatchInsights } from "@/features/library/components/MatchInsights";
import { RallyLanes } from "@/features/library/components/RallyLanes";
import { RallyList } from "@/features/library/components/RallyList";
import { YouTubePlayer, type YouTubePlayerHandle } from "@/features/library/components/YouTubePlayer";
import { useLibraryDoc } from "@/features/library/hooks/useLibraryDoc";
import { useLibraryIndex } from "@/features/library/hooks/useLibraryIndex";
import { fetchMatch } from "@/features/library/libraryData";
import type { MatchDoc, RallyDoc } from "@/features/library/types";

// A rally's end time is when the shuttle lands; give the replay a moment before moving on.
const POINT_END_GRACE_SEC = 1;

function loadMatch(id: string, fixture: boolean) {
  // DEV ONLY: /matches/<any>?fixture=1 renders a bundled fixture instead of Firestore, for
  // working on the page without credentials. `import.meta.env.DEV` is false in production
  // builds, so this branch and the fixture chunk are dropped.
  if (import.meta.env.DEV && fixture) {
    return import("@/features/library/__fixtures__/match.json").then((m) =>
      ok(m.default as unknown as MatchDoc),
    );
  }
  return fetchMatch(id);
}

function Match({ match, editionLabel }: { match: MatchDoc; editionLabel?: string }) {
  const playerRef = useRef<YouTubePlayerHandle>(null);
  const [selected, setSelected] = useState<number | null>(match.rallies[0]?.n ?? null);
  const rally = match.rallies.find((r) => r.n === selected) ?? null;
  const seek = (sec: number) => playerRef.current?.seekTo(sec);

  const selectRally = (r: RallyDoc) => {
    setSelected(r.n);
    seek(r.startSec);
  };

  // Follow the video: select the rally being played, or the last one played while
  // the video is between rallies. A rally counts from its seek target (start minus
  // the lead-in), so jumping to a rally selects that rally, not the one before it.
  // Follow the video: stay on a rally until its point ends, then jump ahead to the next one.
  const followVideo = (sec: number) => {
    const current = match.rallies.find((r) => sec < r.endSec + POINT_END_GRACE_SEC);
    if (current && current.n !== selected) setSelected(current.n);
  };

  return (
    <>
      <title>{`${match.players.A.name} v ${match.players.B.name} | Shuttleye`}</title>
      {match.status === "unpublished" && (
        <p role="status" className="mb-4 rounded-xl border border-border bg-muted px-4 py-2.5 text-sm font-medium">
          Unpublished — only you can see this
        </p>
      )}
      <MatchHeader match={match} editionLabel={editionLabel} />
      <div className="grid gap-6 min-[900px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          <YouTubePlayer
            ref={playerRef}
            videoId={match.youtubeId}
            title={`${match.players.A.name} v ${match.players.B.name}`}
            onTime={followVideo}
          />
          {rally && <RallyLanes rally={rally} players={match.players} onSeek={seek} />}
        </div>
        <RallyList
          rallies={match.rallies}
          players={match.players}
          selected={selected}
          onSelect={selectRally}
          className="min-[900px]:self-start"
        />
      </div>
      <MatchInsights insights={match.insights} players={match.players} onSeek={seek} />
    </>
  );
}

export default function MatchPage() {
  const { matchId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const fixture = searchParams.has("fixture");
  const state = useLibraryDoc(() => loadMatch(matchId, fixture), [matchId, fixture]);
  // The edition name comes from the index; until it loads the header builds one from the id.
  const index = useLibraryIndex(fixture);
  const editionLabel =
    state.status === "ready" && index.status === "ready"
      ? index.data.editions.find((e) => e.id === state.data.editionId)?.name
      : undefined;

  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-8 min-[760px]:px-12">
      <main>
        {state.status === "loading" && <p className="text-muted-foreground">Loading match…</p>}
        {state.status === "error" && (
          <p className="text-muted-foreground">
            {state.error.kind === "network"
              ? `Couldn't load this match: ${state.error.message}`
              : "Match not found."}
          </p>
        )}
        {state.status === "ready" && <Match key={state.data.id} match={state.data} editionLabel={editionLabel} />}
      </main>
    </div>
  );
}
