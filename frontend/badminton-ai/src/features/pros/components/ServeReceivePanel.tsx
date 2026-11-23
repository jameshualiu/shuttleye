import { compare, count } from "../pairFormat";
import type { Finding, PairPlayer, PairView } from "../types";
import { KindBadge } from "./FindingsPanel";
import { Panel } from "./Panel";
import { ShareList, StatRow, Subsection } from "./PairStat";

type ServeReceivePanelProps = {
  view: PairView;
  players: [PairPlayer, PairPlayer];
  /** False for one-match pairs: no ranks, findings or summary. */
  ranked: boolean;
  /** True in a tournament or match view. */
  filtered: boolean;
  className?: string;
};

const placementLabels = [
  ["centre", "Centre"],
  ["middle", "Middle"],
  ["wide", "Wide"],
  ["backCentre", "Back centre"],
  ["backWide", "Back wide"],
] as const;

const returnLabels: [string, string][] = [
  ["net shot", "Net shot"],
  ["push", "Push"],
  ["smash", "Smash"],
  ["lift", "Lift"],
  ["drive", "Drive"],
  ["clear", "Clear"],
  ["drop", "Drop"],
];

function Findings({ findings, ranked, filtered }: { findings: Finding[]; ranked: boolean; filtered: boolean }) {
  const empty = filtered
    ? "Findings use all matches. Choose All matches to see them."
    : ranked
      ? "Nothing stands far out from other pairs in this data."
      : "Not ranked: only one match in the data.";

  return (
    <Subsection title="What stands out">
      {findings.length === 0 ? (
        <p className="text-muted-foreground">{empty}</p>
      ) : (
        <ul className="grid gap-2">
          {findings.map((f) => (
            <li key={f.key} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 rounded-xl bg-muted/60 p-4">
              <span className="font-medium">
                <KindBadge kind={f.kind} />
                {f.claim}
              </span>
              <span className="font-semibold tabular-nums">{f.figure}</span>
              <span className="col-span-full text-sm text-muted-foreground">{f.comparison}</span>
              {f.tip && (
                <span className="col-span-full mt-2 text-sm">
                  <strong className="font-semibold">Try this.</strong> {f.tip}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Subsection>
  );
}

/** Who serves / who receives, by the man's and woman's share (mixed doubles only). */
function MixedSplit({ view, players }: { view: PairView; players: [PairPlayer, PairPlayer] }) {
  if (!view.mixed) return null;
  const man = players.find((p) => p.gender === "Male");
  const woman = players.find((p) => p.gender === "Female");
  const manName = man?.name ?? "The man";
  const womanName = woman?.name ?? "The woman";
  const { serveBy, receiveBy } = view.mixed;

  return (
    <div className="grid grid-cols-2 gap-x-10 gap-y-6 max-[760px]:grid-cols-1">
      <Subsection title="Who serves">
        <ShareList
          title="Share of their serves"
          rows={[
            { label: manName, value: serveBy.man },
            { label: womanName, value: serveBy.woman },
          ]}
        />
      </Subsection>
      <Subsection title="Who receives">
        <ShareList
          title="Share of their returns"
          rows={[
            { label: manName, value: receiveBy.man },
            { label: womanName, value: receiveBy.woman },
          ]}
        />
      </Subsection>
    </div>
  );
}

export function ServeReceivePanel({ view, players, ranked, filtered, className }: ServeReceivePanelProps) {
  const { serve, receive, first4 } = view;
  const rallies = count(view.rallies, "rally", "rallies");

  return (
    <Panel
      title="Serve & receive"
      subtitle="Where doubles rallies are won and lost: the serve, the return and the first shots after them."
      className={className}
    >
      <div className="grid grid-cols-12 gap-x-10 gap-y-8 max-[1180px]:grid-cols-1">
        <div className="col-span-4 min-w-0 max-[1180px]:col-span-1">
          <Findings findings={view.findings} ranked={ranked} filtered={filtered} />
        </div>

        <div className="col-span-8 grid min-w-0 gap-y-8 max-[1180px]:col-span-1">
          <div className="grid grid-cols-2 gap-x-10 gap-y-8 max-[760px]:grid-cols-1">
            <Subsection title="When they serve" sample={count(serve.serves, "serve", "serves")}>
              <StatRow label="Short serves" value={serve.shortShare} {...compare(view, "serve.short_share")} />
              <StatRow
                label="Rallies won"
                hint="Of the rallies they serve"
                value={serve.winRate}
                {...compare(view, "serve.win_rate")}
              />
              <StatRow
                label="Third shot down"
                hint="Their third shot is a smash, drop or push"
                value={serve.thirdDown}
                {...compare(view, "serve.third_down")}
              />
              <ShareList
                title="Where the receiver met the serve"
                rows={placementLabels.map(([key, label]) => ({ label, value: serve.placement[key] }))}
              />
            </Subsection>

            <Subsection title="When they receive" sample={count(receive.returns, "return", "returns")}>
              <StatRow
                label="Attacking returns"
                hint="A smash, drop or push off the serve"
                value={receive.attackShare}
                {...compare(view, "receive.attack_share")}
              />
              <StatRow
                label="Rallies won"
                hint="Of the rallies they receive"
                value={receive.winRate}
                {...compare(view, "receive.win_rate")}
              />
              <ShareList
                title="Return mix"
                rows={returnLabels.map(([key, label]) => ({ label, value: receive.mix[key] ?? null }))}
              />
            </Subsection>
          </div>

          <Subsection title="First 4 shots" sample={rallies}>
            <div className="grid grid-cols-2 gap-x-10 max-[760px]:grid-cols-1">
              <div>
                <StatRow
                  label="Rallies over within 4 shots"
                  value={first4.share}
                  {...compare(view, "first4.share")}
                />
              </div>
              <div>
                <StatRow
                  label="Won of those rallies"
                  value={first4.winRate}
                  {...compare(view, "first4.win_rate")}
                />
              </div>
            </div>
          </Subsection>

          <MixedSplit view={view} players={players} />
        </div>
      </div>
    </Panel>
  );
}
