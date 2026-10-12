import { Play } from "lucide-react";
import { forwardRef, type RefObject } from "react";
import { motion } from "motion/react";
import { AnalysisVideoPlayer } from "../analysis/components/AnalysisVideoPlayer";
import LiveTracker from "../analysis/components/LiveTracker";
import { ShotLog } from "../analysis/components/ShotLog";
import type { CurrentTimeStore } from "../analysis/hooks/useCurrentTimeStore";
import type { DemoState } from "./useDemoAnalysis";

interface Props {
  demo: DemoState;
  store: CurrentTimeStore;
  videoRef: RefObject<HTMLVideoElement | null>;
  showPlayButton: boolean;
  onPlay: () => void;
}

// The Overview tab's layout (shot log | video | rally map) driven by the demo
// clip. On narrow screens the video goes first, then the two side panels.
export const DemoHero = forwardRef<HTMLDivElement, Props>(function DemoHero(
  { demo, store, videoRef, showPlayButton, onPlay },
  ref,
) {
  if (demo.status === "unavailable") return null;

  return (
    <motion.div
      ref={ref}
      className="max-w-6xl mx-auto mt-16 md:mt-20 bg-white/70 dark:bg-card/60 backdrop-blur-md border border-border rounded-2xl overflow-hidden"
      initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.5 }}
    >
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border text-[11px] font-semibold">
        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
        Sample match
      </div>

      {demo.status === "loading" ? (
        <div className="h-[420px] md:h-[480px] flex items-center justify-center">
          <div className="w-8 h-8 border-[3px] border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid gap-3 p-3 md:grid-cols-2 lg:grid-cols-[240px_minmax(0,1fr)_260px]">
          <div className="relative md:col-span-2 lg:col-span-1 lg:order-2 flex flex-col">
            <AnalysisVideoPlayer
              videoRef={videoRef}
              src={demo.clip.videoUrl}
              analysisData={demo.data}
              store={store}
              title="Sample match"
              duration={demo.durationSec}
              shotEvents={demo.data.events}
              fps={demo.fps}
              aspectRatio={demo.aspectRatio}
              videoProps={{
                muted: true,
                loop: true,
                playsInline: true,
                preload: "auto",
                poster: demo.clip.posterUrl,
                onLoadedMetadata: (e) => {
                  e.currentTarget.currentTime = demo.startSec;
                },
              }}
            />
            {showPlayButton && (
              <button
                onClick={onPlay}
                aria-label="Play demo"
                className="cursor-pointer absolute inset-x-0 top-0 flex items-center justify-center rounded-t-xl bg-black/30"
                style={demo.aspectRatio ? { aspectRatio: demo.aspectRatio } : { bottom: 0 }}
              >
                <span className="w-14 h-14 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-lg">
                  <Play className="w-6 h-6 ml-0.5" fill="currentColor" />
                </span>
              </button>
            )}
          </div>

          {/* Side panels are absolutely filled at lg so a long shot list can't
              stretch the row; the video's own shape sets the height there. */}
          <div className="h-[260px] lg:h-auto relative lg:order-1">
            <div className="absolute inset-0 flex [&>*]:flex-1 [&>*]:min-h-0">
              <ShotLog shotEvents={demo.data.events} fps={demo.fps} videoRef={videoRef} status="done" store={store} />
            </div>
          </div>
          <div className="h-[340px] lg:h-auto relative lg:order-3">
            <div className="absolute inset-0 flex [&>*]:flex-1 [&>*]:min-h-0">
              <LiveTracker analysisData={demo.data} store={store} />
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
});
