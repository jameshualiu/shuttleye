import { shotColor } from "../../../utils/shotUtils";
import { fmtTime } from "../../../utils/timeUtils";
import type { AnalysisShot } from "../types";

const RALLY_TILE_BG = "rgba(255,255,255,0.03)";
const RALLY_TILE_BORDER = "1px solid rgba(255,255,255,0.07)";
const RALLY_PROGRESS_TRACK_BG = "rgba(255,255,255,0.06)";
const RALLY_LONG_BORDER = "2px solid rgba(245,158,11,0.4)";
const RALLY_GRADIENT_LONG = "linear-gradient(90deg,#f59e0b,#d97706)";
const RALLY_GRADIENT_DEFAULT = "linear-gradient(90deg,#3B82F6,#0891b2)";

interface Props {
  rallies: AnalysisShot[][];
  fps: number;
  onSeek?: (sec: number) => void;
}

export function RallyLog({ rallies, fps, onSeek }: Props) {
  if (rallies.length === 0) return null;
  return (
    <div className="dark:bg-card bg-white border border-border rounded-xl overflow-hidden shrink-0">
      <div className="py-2.5 px-5 border-b border-border flex items-center justify-between">
        <span className="text-[10px] font-bold tracking-[1.2px] uppercase text-slate-500 dark:text-slate-400">
          Rally Log
        </span>
        <span className="text-[11px] text-slate-500 dark:text-slate-400">
          {rallies.length} {rallies.length === 1 ? "rally" : "rallies"} · avg{" "}
          {Math.round(
            rallies.reduce((s, r) => s + r.length, 0) / rallies.length,
          )}{" "}
          shots
        </span>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-4 gap-3 p-4 border-b border-border">
        {[
          { label: "Rallies", value: rallies.length, color: "text-primary" },
          {
            label: "Longest",
            value: Math.max(...rallies.map((r) => r.length)),
            sub: "shots",
            color: "text-amber-400",
          },
          {
            label: "Avg length",
            value: (
              rallies.reduce((s, r) => s + r.length, 0) / rallies.length
            ).toFixed(1),
            sub: "shots",
            color: "text-foreground",
          },
          {
            label: "> 5 shots",
            value: `${Math.round((rallies.filter((r) => r.length > 5).length / rallies.length) * 100)}%`,
            color: "text-green-400",
          },
        ].map(({ label, value, sub, color }) => (
          <div
            key={label}
            className="rounded-lg p-3"
            style={{ background: RALLY_TILE_BG, border: RALLY_TILE_BORDER }}
          >
            <div className="text-[9px] font-bold uppercase tracking-[.8px] text-slate-500 dark:text-slate-400 mb-1">
              {label}
            </div>
            <div className={`text-[22px] font-bold tracking-tight tabular-nums ${color}`}>
              {value}
            </div>
            {sub && (
              <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                {sub}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Rally rows */}
      <div
        className="overflow-y-auto max-h-[220px] [&::-webkit-scrollbar]:w-[3px] [&::-webkit-scrollbar-thumb]:bg-primary/20 [&::-webkit-scrollbar-thumb]:rounded-full"
      >
        {rallies.map((rally, i) => {
          const startSec = rally[0].frame / fps;
          const endSec = rally[rally.length - 1].frame / fps;
          const durationSec = endSec - startSec;
          const isLong = rally.length > 5;
          return (
            <div
              key={i}
              className="flex items-center gap-4 px-5 py-3 border-b border-slate-100 dark:border-border/40 cursor-pointer hover:bg-primary/5 transition-colors"
              style={isLong ? { borderLeft: RALLY_LONG_BORDER } : {}}
              onClick={() => onSeek?.(startSec)}
            >
              <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 w-5 shrink-0">
                #{i + 1}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] text-slate-400 dark:text-slate-500 mb-1.5 tabular-nums">
                  {fmtTime(startSec)} – {fmtTime(endSec)} · {Math.round(durationSec)}s
                </div>
                {/* Progress bar proportional to shot count */}
                <div
                  className="h-[3px] rounded-full mb-1.5 overflow-hidden"
                  style={{ background: RALLY_PROGRESS_TRACK_BG }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(rally.length / Math.max(...rallies.map((r) => r.length))) * 100}%`,
                      background: isLong ? RALLY_GRADIENT_LONG : RALLY_GRADIENT_DEFAULT,
                    }}
                  />
                </div>
                {/* Shot type dots */}
                <div className="flex gap-1 flex-wrap">
                  {rally.map((s, j) => (
                    <span
                      key={j}
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: shotColor(s.type) }}
                    />
                  ))}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div
                  className={`text-[15px] font-bold tabular-nums leading-none ${isLong ? "text-amber-400" : "text-foreground"}`}
                >
                  {rally.length}
                </div>
                <div className="text-[9px] text-slate-500 dark:text-slate-400 mt-0.5">
                  shots
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {rallies.length > 8 && (
        <div className="py-2.5 text-center text-[11px] text-slate-500 dark:text-slate-400">
          Showing all {rallies.length} rallies
        </div>
      )}
    </div>
  );
}
