import type { Timestamp } from "firebase/firestore";
import { useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { fmtTime } from "../utils/timeUtils";
import LiveTracker from "../features/analysis/components/LiveTracker";
import { ShotLog } from "../features/analysis/components/ShotLog";
import { ShotStatsTab } from "../features/analysis/components/ShotStatsTab";
import { RallyLog } from "../features/analysis/components/RallyLog";
import { AnalysisVideoPlayer } from "../features/analysis/components/AnalysisVideoPlayer";
import { useAnalysisData } from "../features/analysis/hooks/useAnalysisData";
import { useCurrentTimeStore } from "../features/analysis/hooks/useCurrentTimeStore";
import { groupRallies } from "../features/analysis/rallies";
import type { AnalysisShot } from "../features/analysis/types";

function fmtDate(ts: Timestamp | undefined): string {
  if (!ts?.toDate) return "";
  return ts
    .toDate()
    .toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function AnalysisPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const { docData, loading, urls, analysisData, status, resultsError, retryAnalysisData } =
    useAnalysisData(videoId);

  const timeStore = useCurrentTimeStore();
  const [activeTab, setActiveTab] = useState<"overview" | "shot-stats">("overview");

  const videoRef = useRef<HTMLVideoElement | null>(null);

  const duration = docData?.duration ?? 0;

  const shotEvents = useMemo<AnalysisShot[]>(
    () => analysisData?.events ?? [],
    [analysisData],
  );

  const shuttleVisibility = useMemo(() => {
    if (!analysisData?.shuttle_debug?.length) return null;
    const detected = analysisData.shuttle_debug.filter((s) => s.pos !== null).length;
    const total = analysisData.shuttle_debug.length;
    return { detected, total, pct: Math.round((detected / total) * 100) };
  }, [analysisData]);

  const fps = useMemo(() => {
    if (!analysisData?.summary) return 30;
    const dur = analysisData.summary.durationSec;
    const maxFrame = Math.max(
      ...(analysisData.shuttle_debug?.map((s) => s.frame) ?? [0]),
      ...(analysisData.tracking?.map((t) => t.frame) ?? [0]),
    );
    return dur > 0 && maxFrame > 0 ? maxFrame / dur : 30;
  }, [analysisData]);

  const rallies = useMemo(
    () => groupRallies(shotEvents, fps),
    [shotEvents, fps],
  );

  const metaLine = [
    fmtDate(docData?.createdAt),
    duration ? fmtTime(duration) : null,
    docData?.totalShots != null ? `${docData.totalShots} shots detected` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const TABS = [
    { id: "overview" as const, label: "Overview" },
    { id: "shot-stats" as const, label: "Shot Stats" },
  ];

  return (
    <main className="flex-1 flex flex-col min-w-0 overflow-y-auto w-full"><div className="max-w-[1500px] mx-auto px-8 py-8 flex flex-col gap-6 w-full">
      {loading ? (
        <div className="flex items-center justify-center p-8 text-[14px] text-slate-500 dark:text-slate-400">
          Loading your analysis…
        </div>
      ) : !docData ? (
        <div className="flex items-center justify-center p-8 text-[14px] text-slate-500 dark:text-slate-400">
          Analysis not found
        </div>
      ) : (
        <>
          {/* Page header */}
          <div className="flex items-center justify-between shrink-0">
            <div>
              <div className="text-[24px] font-semibold tracking-[-0.6px]">
                {docData.title ?? "Match Analysis"}
              </div>
              {metaLine && (
                <div className="text-[14px] text-slate-500 dark:text-slate-400 mt-0.5 font-light">
                  {metaLine}
                </div>
              )}
            </div>
            {analysisData?.summary?.truncated && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-500 shrink-0">
                Truncated — showing a partial result
              </span>
            )}
          </div>

          {/* Tabs */}
          <div className="flex border-b border-border shrink-0 -mb-2">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-5 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ${
                  activeTab === tab.id
                    ? "border-primary text-foreground"
                    : "border-transparent text-slate-500 dark:text-slate-400 hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {resultsError && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center justify-between gap-3 shrink-0">
              <span>Couldn't load the full analysis data. Shot log, rally map, and stats may be missing.</span>
              <button
                onClick={retryAnalysisData}
                className="text-[12px] font-semibold underline underline-offset-2 shrink-0 cursor-pointer"
              >
                Retry
              </button>
            </div>
          )}

          {/* ── OVERVIEW TAB ── */}
          {activeTab === "overview" && (
            <div className="flex flex-col gap-4">
              {/* 3-column grid: shot log | video | rally map */}
              <div
                className="grid gap-4 items-stretch"
                style={{
                  gridTemplateColumns: "260px minmax(0,1fr) 300px",
                  gridTemplateRows: "clamp(540px, 65vh, 780px)",
                }}
              >
                {/* Shot log */}
                <ShotLog
                  shotEvents={shotEvents}
                  fps={fps}
                  videoRef={videoRef}
                  status={status}
                  store={timeStore}
                />

                {/* Video player */}
                <AnalysisVideoPlayer
                  videoRef={videoRef}
                  src={urls.annotatedVideo || urls.originalVideo}
                  analysisData={analysisData}
                  store={timeStore}
                  title={docData.title ?? videoId ?? ""}
                  duration={duration}
                  shotEvents={shotEvents}
                  fps={fps}
                />

                {/* Live rally map */}
                <LiveTracker analysisData={analysisData} store={timeStore} />
              </div>

              {/* Tracking mini-stats row */}
              {analysisData && (
                <div className="grid grid-cols-4 gap-3 shrink-0">
                  {[
                    {
                      label: "Total shots",
                      value: docData.totalShots ?? "—",
                      color: "text-primary",
                    },
                    {
                      label: "Shuttle visibility",
                      value: shuttleVisibility ? `${shuttleVisibility.pct}%` : "—",
                      color: "text-primary",
                    },
                    {
                      label: "Duration",
                      value: duration ? fmtTime(duration) : "—",
                      color: "text-foreground",
                    },
                    {
                      label: "Court detected",
                      value: analysisData.geometry?.court_keypoints_6 ? "Yes" : "No",
                      color: analysisData.geometry?.court_keypoints_6
                        ? "text-green-400"
                        : "text-slate-400",
                    },
                  ].map(({ label, value, color }) => (
                    <div
                      key={label}
                      className="dark:bg-card bg-white border border-border rounded-xl p-4"
                    >
                      <div className="text-[10px] font-bold tracking-[.8px] uppercase text-slate-500 dark:text-slate-400 mb-1">
                        {label}
                      </div>
                      <div className={`text-[20px] font-bold tracking-tight tabular-nums ${color}`}>
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Rally log */}
              <RallyLog
                rallies={rallies}
                fps={fps}
                onSeek={(t) => {
                  if (videoRef.current) videoRef.current.currentTime = t;
                }}
              />
            </div>
          )}

          {/* ── SHOT STATS TAB ── */}
          {activeTab === "shot-stats" && (
            <ShotStatsTab
              shotEvents={shotEvents}
              totalShots={docData.totalShots}
              status={status}
            />
          )}
        </>
      )}
    </div></main>
  );
}
