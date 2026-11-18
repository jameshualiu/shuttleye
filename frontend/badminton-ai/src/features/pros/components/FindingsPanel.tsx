import type { Clip, Finding } from "../types";
import { cn } from "@/lib/utils";
import { Panel } from "./Panel";

const focus =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

const rowButton = cn(
  "grid min-h-11 w-full cursor-pointer grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 rounded-xl p-4 text-left transition-colors hover:bg-muted/60 aria-pressed:bg-muted",
  focus,
);

type FindingsPanelProps = {
  findings: Finding[];
  selected: number;
  onSelect: (index: number) => void;
  className?: string;
};

export function FindingsPanel({ findings, selected, onSelect, className }: FindingsPanelProps) {
  if (findings.length === 0) {
    return (
      <Panel title="What stands out" className={className}>
        <p className="text-muted-foreground">Nothing stands far out from other pros in this data</p>
      </Panel>
    );
  }

  return (
    <Panel title="What stands out" subtitle="Pick one to watch it" className={className}>
      <ul className="grid gap-2">
        {findings.map((f, i) => (
          <li key={f.key}>
            <button
              type="button"
              aria-pressed={i === selected}
              onClick={() => onSelect(i)}
              className={rowButton}
            >
              <span className="font-medium">
                {f.kind === "strength" && (
                  <span className="mr-1.5 rounded-full bg-foreground px-2 py-0.5 align-[1px] text-xs font-semibold text-background">
                    Strength
                  </span>
                )}
                {f.kind === "weakness" && (
                  <span className="mr-1.5 rounded-full border border-muted-foreground px-2 py-0.5 align-[1px] text-xs font-semibold text-foreground">
                    Weakness
                  </span>
                )}
                {f.claim}
              </span>
              <span className="font-semibold tabular-nums">{f.figure}</span>
              <span className="col-span-full text-sm text-muted-foreground">{f.comparison}</span>
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

type RallyListPanelProps = {
  clips: Clip[];
  selected: number;
  onSelect: (index: number) => void;
  className?: string;
};

/** Filtered views: replaces the findings with a list of the selection's rallies. */
export function RallyListPanel({ clips, selected, onSelect, className }: RallyListPanelProps) {
  const multiMatch = new Set(clips.map((c) => c.matchLabel)).size > 1;
  return (
    <Panel
      title="Rallies in this selection"
      subtitle={`${clips.length.toLocaleString("en-US")} rallies`}
      className={className}
    >
      {clips.length === 0 ? (
        <p className="text-muted-foreground">No clips available for these matches yet</p>
      ) : (
        <ul className="-mx-2 grid max-h-[520px] gap-1 overflow-y-auto px-2 py-1">
          {clips.map((c, i) => (
            <li key={`${i}-${c.youtubeId}-${c.startSec}`}>
              <button
                type="button"
                aria-pressed={i === selected}
                onClick={() => onSelect(i)}
                className={cn(rowButton, "py-2.5")}
              >
                <span className="font-medium first-letter:uppercase">{c.scoreLabel}</span>
                <span className="text-sm tabular-nums text-muted-foreground">{i + 1}</span>
                {multiMatch && (
                  <span className="col-span-full text-sm text-muted-foreground">
                    {c.matchLabel}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
