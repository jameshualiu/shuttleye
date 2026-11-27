import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Insights, Share, ShareMap } from "../types";
import { shotFill } from "./shotColors";

// The six per-player insights (data-flow.md section 8, `Insights`). Shared by
// the match page and the library player profile. Null values are below the
// minimum sample, or (for the score-dependent ones) the rally winners weren't read.

export const SCORE_NOTE = "Shown only for matches whose score we can read.";

const MIX_GROUPS = ["Smash", "Clear", "Drop", "Net", "Block", "Lift", "Drive", "Push"] as const;

const PHASES: { key: keyof Insights["phaseMix"]; label: string }[] = [
  { key: "start", label: "Shots 1–4" },
  { key: "mid", label: "Shots 5–12" },
  { key: "late", label: "Shot 13 on" },
];

const ZONE_ROWS = [
  ["front-left", "front-right"],
  ["mid-left", "mid-right"],
  ["rear-left", "rear-right"],
] as const;

const pct = (v: number) => `${Math.round(v)}%`;

function Card({
  title,
  question,
  children,
  className,
}: {
  title: string;
  question: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-2xl bg-card p-5 text-card-foreground", className)}>
      <h3 className="text-[15px] font-semibold">{title}</h3>
      <p className="mb-4 mt-0.5 text-[13px] text-muted-foreground">{question}</p>
      {children}
    </section>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function Stack({ mix }: { mix: ShareMap }) {
  const parts = MIX_GROUPS.map((g) => ({ g, v: mix[g] ?? 0 })).filter((p) => p.v > 0);
  return (
    <div className="flex h-3.5 overflow-hidden rounded bg-muted-foreground/15">
      {parts.map(({ g, v }) => (
        <i key={g} title={`${g} ${v}%`} className="block h-full" style={{ width: `${v}%`, background: shotFill(g) }} />
      ))}
    </div>
  );
}

/** A labelled stacked bar, or a "too few" note when the mix is below its sample. */
function MixRow({ label, mix }: { label: string; mix: ShareMap | undefined }) {
  const shots = mix?.shots ?? 0;
  const known = mix ? MIX_GROUPS.some((g) => mix[g] != null) : false;
  return (
    <div className="grid grid-cols-[84px_1fr] items-center gap-3 text-xs text-muted-foreground">
      <span>{label}</span>
      {known && mix ? <Stack mix={mix} /> : <span>Too few shots ({shots})</span>}
    </div>
  );
}

function MixLegend() {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-2.5 gap-y-1 text-[11px] text-muted-foreground">
      {MIX_GROUPS.map((g) => (
        <li key={g} className="inline-flex items-center gap-1">
          <i aria-hidden="true" className="inline-block size-2 rounded-[2px]" style={{ background: shotFill(g) }} />
          {g}
        </li>
      ))}
    </ul>
  );
}

function Big({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-[22px] font-semibold tabular-nums">
        {value}
        {unit && <small className="ml-1 text-xs font-normal text-muted-foreground">{unit}</small>}
      </div>
    </div>
  );
}

function Meter({ value }: { value: number }) {
  return (
    <div className="h-2 overflow-hidden rounded bg-muted-foreground/15">
      <i className="block h-full rounded bg-foreground" style={{ width: `${value}%` }} />
    </div>
  );
}

function ShotMixCard({ ins }: { ins: Insights }) {
  return (
    <Card title="Shot mix by phase" question="What they chose early in a rally and later">
      <div className="grid gap-2">
        {PHASES.map((p) => (
          <MixRow key={p.key} label={p.label} mix={ins.phaseMix[p.key]} />
        ))}
      </div>
      <MixLegend />
    </Card>
  );
}

function ZonesCard({ ins }: { ins: Insights }) {
  const shown = ZONE_ROWS.flat().some((z) => ins.zones[z] != null);
  const max = Math.max(1, ...ZONE_ROWS.flat().map((z) => ins.zones[z] ?? 0));
  return (
    <Card title="Where they hit from" question="Share of shots from each zone, net at the top">
      {shown ? (
        <div className="grid grid-cols-2 gap-1" aria-label="Court zones">
          {ZONE_ROWS.flat().map((z) => {
            const v = ins.zones[z] ?? 0;
            return (
              <div
                key={z}
                className="relative flex h-8 items-center justify-center overflow-hidden rounded bg-muted-foreground/10 text-xs font-semibold tabular-nums"
                title={z.replace("-", " ")}
              >
                <i
                  aria-hidden="true"
                  className="absolute inset-0 bg-foreground"
                  style={{ opacity: (v / max) * 0.85 }}
                />
                <span className={cn("relative", v / max > 0.5 ? "text-background" : "text-foreground")}>
                  {pct(v)}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <Note>Too few located shots ({ins.zones.shots ?? 0}).</Note>
      )}
    </Card>
  );
}

function BandsCard({ ins, scoreRead }: { ins: Insights; scoreRead: boolean }) {
  return (
    <Card title="Rally length and tempo" question="Rallies won by length; seconds between shots">
      {!scoreRead ? (
        <Note>{SCORE_NOTE}</Note>
      ) : (
        <div className="grid gap-2">
          {ins.bands.map((b) => (
            <div key={b.band} className="grid grid-cols-[112px_1fr_40px] items-center gap-2 text-xs">
              <span className="text-muted-foreground">{b.label}</span>
              {b.winRate === null ? (
                <span className="col-span-2 text-muted-foreground">Too few rallies ({b.rallies})</span>
              ) : (
                <>
                  <Meter value={b.winRate} />
                  <span className="text-right font-semibold tabular-nums">{pct(b.winRate)}</span>
                </>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <Big
          label="Tempo"
          value={ins.tempo.secPerShot === null ? "–" : ins.tempo.secPerShot.toFixed(2)}
          unit={ins.tempo.secPerShot === null ? "too few shots" : "s per shot"}
        />
        <Big
          label="Avg rally"
          value={ins.tempo.rallyShots === null ? "–" : ins.tempo.rallyShots.toFixed(1)}
          unit={ins.tempo.rallyShots === null ? "too few rallies" : "shots"}
        />
      </div>
    </Card>
  );
}

function RepliesCard({ ins }: { ins: Insights }) {
  const rows = Object.entries(ins.replies).filter(([, mix]) => MIX_GROUPS.some((g) => mix[g] != null));
  // Smash first: "what did they do against a smash?" is the usual question.
  rows.sort(([a], [b]) => (a === "Smash" ? -1 : b === "Smash" ? 1 : 0));
  const smashReplies = ins.replies.Smash?.shots ?? 0;
  return (
    <Card title="Replies" question="What they played after each opponent shot">
      {rows.length === 0 ? (
        <Note>Too few replies to show ({smashReplies} to a smash).</Note>
      ) : (
        <>
          <div className="grid gap-2">
            {rows.map(([g, mix]) => (
              <MixRow key={g} label={`After ${g.toLowerCase()}`} mix={mix} />
            ))}
          </div>
          <MixLegend />
        </>
      )}
    </Card>
  );
}

function ScoreFigure({ label, value, scoreRead, unit }: { label: string; value: Share; scoreRead: boolean; unit?: string }) {
  if (value !== null) return <Big label={label} value={pct(value)} unit={unit} />;
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <p className="mt-1 text-xs text-muted-foreground">{scoreRead ? "Too few to show" : SCORE_NOTE}</p>
    </div>
  );
}

// Matches tools/library/insights.py MIN_SERVES: with this many serves, a null
// shortShare means the length (short/long) was not known for enough of them.
const MIN_SERVES = 30;

function ServeCard({ ins, scoreRead }: { ins: Insights; scoreRead: boolean }) {
  const s = ins.serve;
  return (
    <Card title="Serve" question={`Short vs long serve, and points won on serve (${s.serves} serves)`}>
      <div className="grid grid-cols-3 gap-3 max-[420px]:grid-cols-1">
        {s.shortShare === null ? (
          <div>
            <div className="text-xs text-muted-foreground">Short serves</div>
            <p className="mt-1 text-xs text-muted-foreground">
              {s.serves >= MIN_SERVES ? "Serve length not known for these serves" : "Too few serves"}
            </p>
          </div>
        ) : (
          <Big label="Short serves" value={pct(s.shortShare)} />
        )}
        <ScoreFigure label="Won after short" value={s.pointsWonShort} scoreRead={scoreRead} />
        <ScoreFigure label="Won after long" value={s.pointsWonLong} scoreRead={scoreRead} />
      </div>
    </Card>
  );
}

function SmashWinsCard({ ins, scoreRead }: { ins: Insights; scoreRead: boolean }) {
  const { smashes, winShare } = ins.smashWins;
  return (
    <Card title="Winning shots" question={`Rallies won straight after their smash (${smashes} smashes)`}>
      {winShare !== null ? (
        <Big label="Smashes that won the rally" value={pct(winShare)} />
      ) : (
        <Note>{scoreRead ? `Too few smashes to show (${smashes}).` : SCORE_NOTE}</Note>
      )}
    </Card>
  );
}

type InsightCardsProps = {
  insights: Insights;
  className?: string;
};

export function InsightCards({ insights, className }: InsightCardsProps) {
  // Band rallies only count rallies with a read winner: none at all means no score was read.
  const scoreRead = insights.bands.some((b) => b.rallies > 0);
  return (
    <div className={cn("grid grid-cols-3 gap-4 max-[1100px]:grid-cols-2 max-[700px]:grid-cols-1", className)}>
      <ShotMixCard ins={insights} />
      <ZonesCard ins={insights} />
      <BandsCard ins={insights} scoreRead={scoreRead} />
      <RepliesCard ins={insights} />
      <ServeCard ins={insights} scoreRead={scoreRead} />
      <SmashWinsCard ins={insights} scoreRead={scoreRead} />
    </div>
  );
}
