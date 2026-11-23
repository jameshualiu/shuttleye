import { Link, useParams, useSearchParams } from "react-router-dom";
import { Panel } from "@/features/pros/components/Panel";
import { PairHeader } from "@/features/pros/components/PairHeader";
import { ProShell } from "@/features/pros/components/ProShell";
import { RestOfRallyPanel } from "@/features/pros/components/RestOfRallyPanel";
import { ServeReceivePanel } from "@/features/pros/components/ServeReceivePanel";
import { useProData } from "@/features/pros/hooks/useProData";
import { pairName } from "@/features/pros/pairFormat";
import { fetchPair } from "@/features/pros/proData";
import type { PairProfile } from "@/features/pros/types";

function Profile({ pair }: { pair: PairProfile }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("view") ?? "all";
  const viewId = pair.views[requested] ? requested : "all";
  const view = pair.views[viewId];
  const filtered = viewId !== "all";

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
      <title>{`${pairName(pair.players)} | Shuttleye`}</title>
      <PairHeader pair={pair} viewId={viewId} onViewChange={changeView} />
      {view && (
        <div key={viewId} className="grid grid-cols-12 gap-6 max-[900px]:gap-4">
          <ServeReceivePanel
            view={view}
            players={pair.players}
            ranked={pair.ranked}
            filtered={filtered}
            className="col-span-12"
          />
          <RestOfRallyPanel view={view} players={pair.players} className="col-span-12" />
          <Panel title="Watch" className="col-span-12">
            <p className="text-muted-foreground">
              Clips for doubles are coming. They'll be added match by match.
            </p>
          </Panel>
        </div>
      )}
    </>
  );
}

function NotFound() {
  return (
    <div className="py-16">
      <title>Pair not found | Shuttleye</title>
      <h1 className="text-[32px] font-semibold tracking-tight">Not found</h1>
      <p className="mt-2 text-muted-foreground">We don't have a profile for this pair.</p>
      <Link
        to="/pairs"
        className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        See all pairs
      </Link>
    </div>
  );
}

function PairProfileLoader({ pairId }: { pairId: string }) {
  const state = useProData(() => fetchPair(pairId), [pairId]);

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
  if (state.data.id !== pairId) return <NotFound />;
  return <Profile pair={state.data} />;
}

export default function PairProfilePage() {
  const { pairId = "" } = useParams();
  return (
    <ProShell source="doubles">
      <PairProfileLoader key={pairId} pairId={pairId} />
    </ProShell>
  );
}
