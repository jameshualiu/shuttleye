import { useState } from "react";
import { compare, sample } from "../pairFormat";
import type { Finding, PairPlayer, PairView } from "../types";
import { KindBadge } from "./FindingsPanel";
import { Panel } from "./Panel";
import { Group, MoreDetails, ShareList, StatRow, StatStack } from "./PairStat";

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

type CardProps = { view: PairView; className?: string };
type PairCardProps = CardProps & { players: [PairPlayer, PairPlayer] };

type FindingsCardProps = {
  findings: Finding[];
  /** False for one-match pairs: no ranks, findings or summary. */
  ranked: boolean;
  /** True in a tournament or match view. */
  filtered: boolean;
  className?: string;
};

/** What stands out, in the singles style: pick a finding to see its tip. */
export function PairFindingsPanel({ findings, ranked, filtered, className }: FindingsCardProps) {
  const [selected, setSelected] = useState(0);
  const finding = findings[selected];

  if (findings.length === 0) {
    const empty = filtered
      ? "Findings use all matches. Choose All matches to see them."
      : ranked
        ? "Nothing stands far out from other pairs in this data."
        : "Not ranked: only one match in the data.";
    return (
      <Panel title="What stands out" className={className}>
        <p className="text-muted-foreground">{empty}</p>
      </Panel>
    );
  }

  return (
    <Panel title="What stands out" subtitle="Pick one for a tip" className={className}>
      <ul className="grid gap-1">
        {findings.map((f, i) => (
          <li key={f.key}>
            <button
              type="button"
              aria-pressed={i === selected}
              onClick={() => setSelected(i)}
              className="grid min-h-11 w-full cursor-pointer grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 rounded-xl p-4 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-pressed:bg-muted"
            >
              <span className="font-medium">
                <KindBadge kind={f.kind} />
                {f.claim}
              </span>
              <span className="font-semibold tabular-nums">{f.figure}</span>
              <span className="col-span-full text-sm text-muted-foreground">{f.comparison}</span>
            </button>
          </li>
        ))}
      </ul>
      {finding?.tip && (
        <p aria-live="polite" className="mt-4 rounded-xl border border-border p-4">
          <strong className="font-semibold">Try this.</strong> {finding.tip}
        </p>
      )}
    </Panel>
  );
}

type MixedSplitProps = PairCardProps & {
  title: string;
  split: "serveBy" | "receiveBy";
  sampleKey: "mixed.serve_by" | "mixed.receive_by";
};

/** Mixed doubles only: the man's and woman's share of a pair's serves or returns. */
function MixedSplit({ view, players, title, split, sampleKey }: MixedSplitProps) {
  if (!view.mixed) return null;
  const man = players.find((p) => p.gender === "Male")?.name ?? "The man";
  const woman = players.find((p) => p.gender === "Female")?.name ?? "The woman";
  const shares = view.mixed[split];
  return (
    <Group title={title}>
      <ShareList
        sample={sample(view, sampleKey)}
        rows={[
          { label: man, value: shares.man },
          { label: woman, value: shares.woman },
        ]}
      />
    </Group>
  );
}

export function ServePanel({ view, players, className }: PairCardProps) {
  const { serve } = view;
  return (
    <Panel title="When they serve" className={className}>
      <StatStack>
        <StatRow label="Short serves" value={serve.shortShare} {...compare(view, "serve.short_share")} />
        <StatRow label="Rallies won" value={serve.winRate} {...compare(view, "serve.win_rate")} />
        <StatRow
          label="Third shot hit down"
          hint="A smash, drop or push"
          value={serve.thirdDown}
          {...compare(view, "serve.third_down")}
        />
      </StatStack>
      <MixedSplit view={view} players={players} title="Who serves" split="serveBy" sampleKey="mixed.serve_by" />
      <MoreDetails title="Where the receiver met the serve">
        <ShareList
          sample={sample(view, "serve.placement")}
          rows={placementLabels.map(([key, label]) => ({ label, value: serve.placement[key] }))}
        />
      </MoreDetails>
    </Panel>
  );
}

export function ReceivePanel({ view, players, className }: PairCardProps) {
  const { receive } = view;
  return (
    <Panel title="When they receive" className={className}>
      <StatStack>
        <StatRow
          label="Attacking returns"
          hint="A smash, drop or push off the serve"
          value={receive.attackShare}
          {...compare(view, "receive.attack_share")}
        />
        <StatRow label="Rallies won" value={receive.winRate} {...compare(view, "receive.win_rate")} />
      </StatStack>
      <MixedSplit view={view} players={players} title="Who receives" split="receiveBy" sampleKey="mixed.receive_by" />
      <MoreDetails title="Return mix">
        <ShareList
          sample={sample(view, "receive.mix")}
          rows={returnLabels.map(([key, label]) => ({ label, value: receive.mix[key] ?? null }))}
        />
      </MoreDetails>
    </Panel>
  );
}

export function First4Panel({ view, className }: CardProps) {
  const { first4 } = view;
  return (
    <Panel title="The first 4 shots" subtitle="The serve, the return and the next two" className={className}>
      <StatStack>
        <StatRow label="Rallies over within 4 shots" value={first4.share} {...compare(view, "first4.share")} />
        <StatRow label="Won of those rallies" value={first4.winRate} {...compare(view, "first4.win_rate")} />
      </StatStack>
    </Panel>
  );
}
