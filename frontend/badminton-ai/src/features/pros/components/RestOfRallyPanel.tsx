import { compare, count, isShown, pct } from "../pairFormat";
import type { PairPlayer, PairView } from "../types";
import { Panel } from "./Panel";
import { ShareList, StatRow, Subsection } from "./PairStat";

type RestOfRallyPanelProps = {
  view: PairView;
  players: [PairPlayer, PairPlayer];
  className?: string;
};

// rally.lose_reason, from the side of the pair that lost the point.
const lostLabels: [string, string][] = [
  ["opp_winner", "Opponent's winner"],
  ["net_fault", "Their shot into the net"],
  ["out", "Their shot out"],
  ["failed_return", "Their failed return"],
  ["judgment_error", "Their judgment error"],
  ["fault", "Their fault"],
];

function Roles({ view, players }: RestOfRallyPanelProps) {
  const nameOf = (id: string) => players.find((p) => p.id === id)?.name ?? id;
  const cell = (v: number | null) => (isShown(v) ? pct(v) : "–");

  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Each partner's share of the pair's smashes and net shots</caption>
      <thead>
        <tr className="text-muted-foreground">
          <th scope="col" className="py-1.5 text-left font-medium">
            Player
          </th>
          <th scope="col" className="py-1.5 text-right font-medium">
            Smashes
          </th>
          <th scope="col" className="py-1.5 text-right font-medium">
            Net shots
          </th>
        </tr>
      </thead>
      <tbody>
        {view.rest.roles.map((r) => (
          <tr key={r.playerId} className="border-t border-border">
            <th scope="row" className="py-2.5 pr-4 text-left font-medium">
              {nameOf(r.playerId)}
            </th>
            <td className="py-2.5 text-right text-[17px] font-semibold tabular-nums">
              {cell(r.smashShare)}
            </td>
            <td className="py-2.5 text-right text-[17px] font-semibold tabular-nums">
              {cell(r.netShare)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RestOfRallyPanel({ view, players, className }: RestOfRallyPanelProps) {
  const { rest } = view;
  return (
    <Panel
      title="The rest of the rally"
      subtitle={count(view.rallies, "rally", "rallies")}
      className={className}
    >
      <div className="grid grid-cols-3 gap-x-10 gap-y-8 max-[1180px]:grid-cols-2 max-[760px]:grid-cols-1">
        <Subsection title="How they play">
          <StatRow
            label="Attacking shots"
            hint="Smash, drop or push, after the serve"
            value={rest.attackShare}
            {...compare(view, "rally.attack_share")}
          />
          <StatRow
            label="Attacking formation"
            hint="Shots hit while set up to attack"
            value={rest.formationAttack}
            {...compare(view, "rally.formation_attack")}
          />
        </Subsection>

        <Subsection title="Who plays which shots">
          <Roles view={view} players={players} />
        </Subsection>

        <Subsection title="How points end">
          <ShareList
            title="Points lost"
            rows={lostLabels.map(([key, label]) => ({ label, value: rest.pointsLost[key] ?? null }))}
          />
          <ShareList
            title="Points won"
            rows={[
              { label: "Their winner", value: rest.pointsWon.winner },
              { label: "Opponent's error", value: rest.pointsWon.oppError },
            ]}
          />
        </Subsection>
      </div>
    </Panel>
  );
}
