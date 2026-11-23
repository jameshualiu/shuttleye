import { cn } from "@/lib/utils";
import { compare, isShown, pct, sample } from "../pairFormat";
import type { PairPlayer, PairView } from "../types";
import { Panel } from "./Panel";
import { Group, ShareList, StatRow, StatStack } from "./PairStat";

type CardProps = { view: PairView; className?: string };
type PairCardProps = CardProps & { players: [PairPlayer, PairPlayer] };

// rally.lose_reason, from the side of the pair that lost the point.
const lostLabels: [string, string][] = [
  ["opp_winner", "Opponent's winner"],
  ["net_fault", "Into the net"],
  ["out", "Hit out"],
  ["failed_return", "Failed return"],
  ["judgment_error", "Judgment error"],
  ["fault", "Fault"],
];

function Roles({ view, players }: PairCardProps) {
  const nameOf = (id: string) => players.find((p) => p.id === id)?.name ?? id;
  const cell = (v: number | null) => (isShown(v) ? pct(v) : "–");

  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Each partner's share of the pair's smashes and net shots</caption>
      <thead>
        <tr className="text-muted-foreground">
          <th scope="col" className="pb-2 text-left font-medium">
            <span className="sr-only">Player</span>
          </th>
          <th scope="col" className="pb-2 text-right font-medium">
            Smashes
          </th>
          <th scope="col" className="pb-2 pl-4 text-right font-medium">
            Net shots
          </th>
        </tr>
      </thead>
      <tbody>
        {view.rest.roles.map((r) => (
          <tr key={r.playerId}>
            <th scope="row" className="py-1.5 pr-4 text-left font-normal">
              {nameOf(r.playerId)}
            </th>
            <td className="py-1.5 text-right font-semibold tabular-nums">{cell(r.smashShare)}</td>
            <td className="py-1.5 pl-4 text-right font-semibold tabular-nums">{cell(r.netShare)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AttackPanel({ view, players, className }: PairCardProps) {
  const { rest } = view;
  return (
    <Panel title="How they attack" subtitle="Every shot after the serve" className={className}>
      <StatStack>
        <StatRow
          label="Attacking shots"
          hint="A smash, drop or push"
          value={rest.attackShare}
          {...compare(view, "rally.attack_share")}
        />
        <StatRow
          label="Attacking formation"
          hint="Shots hit while set up to attack"
          value={rest.formationAttack}
          {...compare(view, "rally.formation_attack")}
        />
      </StatStack>
      <Group title="Who plays which shots">
        <Roles view={view} players={players} />
      </Group>
    </Panel>
  );
}

export function PointsPanel({ view, className }: CardProps) {
  const { rest } = view;
  return (
    <Panel title="How points end" className={cn("@container", className)}>
      <div className="grid gap-x-10 @2xl:grid-cols-2">
        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">Points they won</h3>
          <ShareList
            sample={sample(view, "points.won")}
            rows={[
              { label: "Their winner", value: rest.pointsWon.winner },
              { label: "Opponent's error", value: rest.pointsWon.oppError },
            ]}
          />
        </div>
        <Group title="Points they lost" className="@2xl:mt-0 @2xl:border-t-0 @2xl:pt-0">
          <ShareList
            sample={sample(view, "points.lost")}
            rows={lostLabels.map(([key, label]) => ({ label, value: rest.pointsLost[key] ?? null }))}
          />
        </Group>
      </div>
    </Panel>
  );
}
