import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { isShown, ordinal, pct } from "../pairFormat";
import type { Finding, Share } from "../types";
import { KindBadge } from "./FindingsPanel";

const TOO_FEW = "Too few to compare";

type SubsectionProps = {
  title: string;
  className?: string;
  children: ReactNode;
};

/** A titled block inside a panel (h3 under the panel's h2). */
export function Subsection({ title, className, children }: SubsectionProps) {
  return (
    <div className={cn("min-w-0", className)}>
      <h3 className="text-[15px] font-semibold text-foreground">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

type StatRowProps = {
  label: string;
  /** A short explanation under the label. */
  hint?: string;
  value: Share;
  /** The typical pair's value (all matches), when the JSON has one. */
  typical?: number;
  rank?: { rank: number; of: number };
  /** The count behind this value, e.g. "381 returns". */
  sample?: string;
};

/** One headline share, its bar with a typical-pair tick, and the comparison line. */
export function StatRow({ label, hint, value, typical, rank, sample }: StatRowProps) {
  const comparison = [
    isShown(value) ? sample : null,
    typical !== undefined ? `Typical pair ${pct(typical)}` : null,
    rank ? `${ordinal(rank.rank)} of ${rank.of}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="border-t border-border py-3 first:border-t-0 first:pt-1">
      <div className="flex items-baseline justify-between gap-4">
        <span className="min-w-0">
          <span className="block font-medium">{label}</span>
          {hint && <span className="block text-sm text-muted-foreground">{hint}</span>}
        </span>
        {isShown(value) ? (
          <span className="text-[22px] font-semibold leading-none tabular-nums">{pct(value)}</span>
        ) : (
          <span className="shrink-0 text-right text-sm tabular-nums text-muted-foreground">
            {sample ? `${sample} · ${TOO_FEW}` : TOO_FEW}
          </span>
        )}
      </div>
      {isShown(value) && (
        <div aria-hidden="true" className="relative mt-2 h-1.5 rounded bg-muted-foreground/15">
          <div
            className="h-full rounded bg-foreground"
            style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
          />
          {typical !== undefined && (
            <div
              className="absolute -top-1 h-3.5 w-0.5 -translate-x-1/2 rounded bg-muted-foreground"
              style={{ left: `${Math.min(100, Math.max(0, typical))}%` }}
            />
          )}
        </div>
      )}
      {comparison && <p className="mt-1.5 text-sm tabular-nums text-muted-foreground">{comparison}</p>}
    </div>
  );
}

type ShareListProps = {
  /** Visible heading for the list, e.g. "Where the receiver met the serve". */
  title: string;
  rows: { label: string; value: Share }[];
  /** The count behind the shares, e.g. "412 serves". */
  sample?: string;
};

/** A labelled distribution: one small bar per share. Null as a whole shows "Too few to compare". */
export function ShareList({ title, rows, sample }: ShareListProps) {
  const known = rows.some((r) => isShown(r.value));
  return (
    <div className="mt-3">
      <p className="flex flex-wrap items-baseline justify-between gap-x-4 text-sm text-muted-foreground">
        <span className="font-medium">{title}</span>
        {sample && known && <span className="tabular-nums">{sample}</span>}
      </p>
      {known ? (
        <ul className="mt-2 grid gap-1.5 text-sm">
          {rows.map((r) => (
            <li
              key={r.label}
              className="grid grid-cols-[minmax(0,12rem)_minmax(40px,1fr)_3rem] items-center gap-3"
            >
              <span className="truncate" title={r.label}>
                {r.label}
              </span>
              <span aria-hidden="true" className="h-1.5 rounded bg-muted-foreground/15">
                {isShown(r.value) && (
                  <span
                    className="block h-full rounded bg-foreground/70"
                    style={{ width: `${Math.min(100, Math.max(0, r.value))}%` }}
                  />
                )}
              </span>
              <span className="text-right tabular-nums">
                {isShown(r.value) ? pct(r.value) : "–"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm tabular-nums text-muted-foreground">
          {sample ? `${sample} · ${TOO_FEW}` : TOO_FEW}
        </p>
      )}
    </div>
  );
}

/** Findings in the pair-page style: claim, figure, comparison and tip. */
export function FindingList({ findings, className }: { findings: Finding[]; className?: string }) {
  return (
    <ul className={cn("grid gap-2", className)}>
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
  );
}
