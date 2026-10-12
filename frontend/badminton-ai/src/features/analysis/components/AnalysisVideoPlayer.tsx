import { useEffect, useMemo, useRef, useState, type RefObject, type VideoHTMLAttributes } from "react";
import { fmtTime } from "../../../utils/timeUtils";
import type { CurrentTimeStore } from "../hooks/useCurrentTimeStore";
import type { AnalysisData, AnalysisShot, TrackingFrame } from "../types";
import { VideoTimeline } from "./VideoTimeline";

const COCO_PAIRS: [number, number][] = [
  [0, 1], [0, 2], [1, 3], [2, 4], [5, 6], [5, 7], [7, 9],
  [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13],
  [13, 15], [12, 14], [14, 16],
];

// Canvas overlay colors
const COURT_LINE_COLOR = "rgba(137,194,217,0.55)";
const PLAYER_COLORS = ["#89c2d9", "#2c7da0"];
const SHUTTLE_FILL_COLOR = "#fff";

interface Props {
  videoRef: RefObject<HTMLVideoElement | null>;
  src: string | null | undefined;
  analysisData: AnalysisData | null;
  store: CurrentTimeStore;
  title: string;
  duration: number;
  shotEvents: AnalysisShot[];
  fps: number;
  // width / height of the analysed video. The overlay canvas covers the whole
  // stage, so it only lines up with a letterboxed video when the stage has the
  // video's own shape; pass this to size the stage that way. Omitted, the
  // stage fills whatever height its parent gives it.
  aspectRatio?: number;
  // Extra <video> attributes, e.g. muted/loop/playsInline/poster for the landing demo.
  videoProps?: VideoHTMLAttributes<HTMLVideoElement>;
}

// Video with court/pose/shuttle overlays and the shot timeline. Drives `store`
// from the video's currentTime so ShotLog, LiveTracker etc. stay in sync.
export function AnalysisVideoPlayer({
  videoRef,
  src,
  analysisData,
  store,
  title,
  duration,
  shotEvents,
  fps,
  aspectRatio,
  videoProps,
}: Props) {
  const [ov, setOv] = useState({ court: true, pose: true, shuttle: true });
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const renderOverlayRef = useRef<() => void>(() => {});
  const animRef = useRef<number | null>(null);

  const trackingByFrame = useMemo(() => {
    const m = new Map<number, TrackingFrame>();
    analysisData?.tracking?.forEach((e) => m.set(e.frame, e));
    return m;
  }, [analysisData]);

  const shuttleByFrame = useMemo(() => {
    const m = new Map<
      number,
      { frame: number; pos: [number, number] | null; confidence: number }
    >();
    analysisData?.shuttle_debug?.forEach((e) => m.set(e.frame, e));
    return m;
  }, [analysisData]);

  // Keep renderOverlayRef fresh
  useEffect(() => {
    renderOverlayRef.current = () => {
      const canvas = overlayRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      if (!analysisData?.summary) return;

      const res = analysisData.summary.resolution;
      const sx = w / res[0], sy = h / res[1];
      const sc = (pt: [number, number]): [number, number] => [pt[0] * sx, pt[1] * sy];
      const dur = analysisData.summary.durationSec;
      const maxFrame = Math.max(
        ...(analysisData.shuttle_debug?.map((s) => s.frame) ?? [0]),
        ...(analysisData.tracking?.map((t) => t.frame) ?? [0]),
      );
      const fps = dur > 0 && maxFrame > 0 ? maxFrame / dur : 30;
      const frame = Math.round((videoRef.current?.currentTime ?? 0) * fps);

      if (ov.court && analysisData.geometry?.court_keypoints_35) {
        const kp = analysisData.geometry.court_keypoints_35;
        ctx.strokeStyle = COURT_LINE_COLOR;
        ctx.lineWidth = 1.5;
        for (let row = 0; row < 7; row++) {
          for (let col = 0; col < 5; col++) {
            const idx = row * 5 + col;
            if (!kp[idx]) continue;
            const [x, y] = sc(kp[idx]);
            if (col < 4 && kp[idx + 1]) {
              const [nx, ny] = sc(kp[idx + 1]);
              ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(nx, ny); ctx.stroke();
            }
            if (row < 6 && kp[idx + 5]) {
              const [nx, ny] = sc(kp[idx + 5]);
              ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(nx, ny); ctx.stroke();
            }
          }
        }
      }

      if (ov.pose && analysisData.tracking?.length) {
        let entry = trackingByFrame.get(frame);
        for (let off = 1; off <= 3 && !entry; off++) {
          entry = trackingByFrame.get(frame - off) ?? trackingByFrame.get(frame + off);
        }
        if (entry) {
          entry.players.forEach((player, pi) => {
            const color = PLAYER_COLORS[pi % 2];
            ctx.strokeStyle = color;
            ctx.lineWidth = 1;
            COCO_PAIRS.forEach(([a, b]) => {
              const pa = player.skeleton[a], pb = player.skeleton[b];
              if (!pa || !pb) return;
              if (pa[0] === 0 && pa[1] === 0) return;
              if (pb[0] === 0 && pb[1] === 0) return;
              const [ax, ay] = sc(pa), [bx, by] = sc(pb);
              ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
            });
            ctx.fillStyle = color;
            player.skeleton.forEach((pt) => {
              if (!pt || (pt[0] === 0 && pt[1] === 0)) return;
              const [x, y] = sc(pt);
              ctx.beginPath(); ctx.arc(x, y, 1.5, 0, Math.PI * 2); ctx.fill();
            });
          });
        }
      }

      if (ov.shuttle && analysisData.shuttle_debug?.length) {
        let entry = shuttleByFrame.get(frame);
        for (let off = 1; off <= 3 && !entry?.pos; off++) {
          entry = shuttleByFrame.get(frame - off) ?? shuttleByFrame.get(frame + off);
        }
        if (entry?.pos) {
          const [x, y] = sc(entry.pos);
          ctx.shadowBlur = 5;
          ctx.shadowColor = PLAYER_COLORS[0];
          ctx.fillStyle = SHUTTLE_FILL_COLOR;
          ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fill();
          ctx.shadowBlur = 0;
        }
      }
    };
  }, [analysisData, ov, trackingByFrame, shuttleByFrame, videoRef]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const update = () => {
      store.set(v.currentTime);
      renderOverlayRef.current();
      animRef.current = requestAnimationFrame(update);
    };
    animRef.current = requestAnimationFrame(update);
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [src, store, videoRef]);

  useEffect(() => {
    const handleResize = () => {
      const c = overlayRef.current;
      if (c && c.clientWidth > 0) {
        c.width = c.clientWidth;
        c.height = c.clientHeight;
        renderOverlayRef.current();
      }
    };
    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const toggleOv = (k: keyof typeof ov) =>
    setOv((prev) => ({ ...prev, [k]: !prev[k] }));

  return (
    <div className="dark:bg-card bg-white border border-border rounded-xl overflow-hidden flex flex-col">
      <div
        className={`relative w-full bg-video-canvas flex items-center justify-center cursor-pointer group overflow-hidden ${
          aspectRatio ? "flex-none" : "flex-1 min-h-0"
        }`}
        style={aspectRatio ? { aspectRatio } : undefined}
      >
        {src ? (
          <video
            ref={videoRef}
            src={src}
            {...videoProps}
            className="w-full h-full object-contain block"
            onClick={(e) => {
              const v = e.currentTarget;
              if (v.paused) v.play();
              else v.pause();
            }}
          />
        ) : (
          <div className="w-12 h-12 rounded-full bg-primary/10 border-[1.5px] border-primary/30 flex items-center justify-center opacity-65 group-hover:opacity-100 transition-opacity">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M5 3l9 5-9 5V3z" fill="currentColor" className="text-primary" />
            </svg>
          </div>
        )}
        <span className="absolute top-3 left-4 text-[11px] text-slate-400 dark:text-slate-500 font-light pointer-events-none">
          {title}
        </span>
        {duration > 0 && (
          <span className="absolute top-3 right-4 text-[11px] text-slate-400 dark:text-slate-500 pointer-events-none">
            {fmtTime(duration)}
          </span>
        )}
        <canvas
          className="absolute inset-0 w-full h-full pointer-events-none"
          ref={overlayRef}
        />
        {analysisData && (
          <div className="absolute bottom-3 left-4 flex gap-2">
            {(["court", "pose", "shuttle"] as const).map((k) => (
              <button
                key={k}
                onClick={() => toggleOv(k)}
                className={`text-[10px] font-medium py-1 px-2.5 rounded-lg border cursor-pointer transition-all ${
                  ov[k]
                    ? "bg-primary/15 border-primary/40 text-primary"
                    : "border-primary/20 bg-video-chrome/80 text-slate-400 dark:text-slate-500"
                }`}
              >
                {k.charAt(0).toUpperCase() + k.slice(1)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Timeline */}
      <VideoTimeline
        duration={duration}
        shotEvents={shotEvents}
        fps={fps}
        videoRef={videoRef}
        store={store}
      />
    </div>
  );
}
