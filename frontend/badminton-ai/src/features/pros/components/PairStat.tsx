import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { isShown, ordinal, pct } from "../pairFormat";
import type { Share } from "../types";

const TOO_FEW = "Too few to compare";

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
    typical !== undefined ? `Typical pair ${pct(typical)}` : null,
    rank ? `${ordinal(rank.rank)} of ${rank.of}` : null,
    sample,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <div className="flex items-baseline justify-between gap-4">
        <span className="min-w-0">
          <span className="block font-medium">{label}</span>
          {hint && <span className="block text-sm text-muted-foreground">{hint}</span>}
        </span>
        {isShown(value) && (
          <span className="text-[22px] font-semibold leading-none tabular-nums">{pct(value)}</span>
        )}
      </div>
      {isShown(value) ? (
        <>
          <div aria-hidden="true" className="relative mt-3 h-1.5 rounded bg-muted-foreground/15">
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
          {comparison && <p className="mt-2 text-sm tabular-nums text-muted-foreground">{comparison}</p>}
        </>
      ) : (
        <p className="mt-1 text-sm tabular-nums text-muted-foreground">
          {sample ? `${TOO_FEW} · ${sample}` : TOO_FEW}
        </p>
      )}
    </div>
  );
}

/** Stat rows stacked with even spacing and a hairline between them. */
export function StatStack({ children }: { children: ReactNode }) {
  return <div className="divide-y divide-border">{children}</div>;
}

type ShareListProps = {
  rows: { label: string; value: Share }[];
  /** The count behind the shares, e.g. "412 serves". */
  sample?: string;
};

/** A distribution: one small bar per share. Null as a whole shows "Too few to compare". */
export function ShareList({ rows, sample }: ShareListProps) {
  const known = rows.some((r) => isShown(r.value));
  if (!known) {
    return (
      <p className="text-sm tabular-nums text-muted-foreground">
        {sample ? `${TOO_FEW} · ${sample}` : TOO_FEW}
      </p>
    );
  }
  return (
    <>
      <ul className="grid gap-2 text-sm">
        {rows.map((r) => (
          <li key={r.label} className="grid grid-cols-[minmax(0,9rem)_minmax(40px,1fr)_3rem] items-center gap-3">
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
            <span className="text-right tabular-nums">{isShown(r.value) ? pct(r.value) : "–"}</span>
          </li>
        ))}
      </ul>
      {sample && <p className="mt-2 text-sm tabular-nums text-muted-foreground">{sample}</p>}
    </>
  );
}

type GroupProps = {
  title: string;
  className?: string;
  children: ReactNode;
};

/** A small titled group inside a card, below its stat rows. */
export function Group({ title, className, children }: GroupProps) {
  return (
    <div className={cn("mt-6 border-t border-border pt-5", className)}>
      <h3 className="mb-3 text-sm font-medium text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}

/** A closed-by-default group for detail most readers can skip. */
export function MoreDetails({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group mt-6 border-t border-border pt-2">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
        {title}
        <svg
          aria-hidden="true"
          width="12"
          height="12"
          viewBox="0 0 12 12"
          className="transition-transform group-open:rotate-180"
        >
          <path
            d="M3 4.5l3 3 3-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </summary>
      <div className="pt-2">{children}</div>
    </details>
  );
}
