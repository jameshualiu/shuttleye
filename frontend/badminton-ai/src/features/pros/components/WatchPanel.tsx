import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Clip } from "../types";
import { cn } from "@/lib/utils";
import { Panel } from "./Panel";

type WatchPanelProps = {
  title: string;
  subtitle?: string;
  clips: Clip[];
  index: number;
  onIndexChange: (index: number) => void;
  tip?: string | null;
  className?: string;
};

const pagerButton = cn(
  "inline-flex size-11 cursor-pointer items-center justify-center rounded-full bg-muted text-foreground transition-opacity aria-disabled:cursor-default aria-disabled:opacity-40",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
);

export function WatchPanel({
  title,
  subtitle,
  clips,
  index,
  onIndexChange,
  tip,
  className,
}: WatchPanelProps) {
  const clip = clips[index] ?? clips[0];
  const current = clip ? clips.indexOf(clip) : 0;

  return (
    <Panel title={title} subtitle={subtitle} className={className}>
      {clip ? (
        <>
          <iframe
            key={`${clip.youtubeId}-${clip.startSec}`}
            src={`https://www.youtube-nocookie.com/embed/${clip.youtubeId}?start=${clip.startSec}&end=${clip.endSec}`}
            title={clip.matchLabel}
            allow="encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
            loading="lazy"
            referrerPolicy="strict-origin-when-cross-origin"
            className="block aspect-video w-full rounded-xl bg-muted"
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            <span className="text-sm text-muted-foreground">
              {clip.matchLabel}, {clip.scoreLabel}
            </span>
            {clips.length > 1 && (
              <span className="flex items-center gap-2 text-sm tabular-nums text-muted-foreground">
                <button
                  type="button"
                  aria-label="Previous rally"
                  aria-disabled={current === 0}
                  onClick={() => current > 0 && onIndexChange(current - 1)}
                  className={pagerButton}
                >
                  <ChevronLeft aria-hidden="true" className="size-4" />
                </button>
                <span aria-live="polite">
                  {current + 1} of {clips.length}
                </span>
                <button
                  type="button"
                  aria-label="Next rally"
                  aria-disabled={current === clips.length - 1}
                  onClick={() => current < clips.length - 1 && onIndexChange(current + 1)}
                  className={pagerButton}
                >
                  <ChevronRight aria-hidden="true" className="size-4" />
                </button>
              </span>
            )}
          </div>
        </>
      ) : (
        <div className="flex aspect-video w-full items-center justify-center rounded-xl bg-muted p-6 text-center text-muted-foreground">
          No clips available for these matches yet
        </div>
      )}
      {tip && (
        <p className="mt-6 rounded-xl bg-muted p-4">
          <strong className="font-semibold">Try this.</strong> {tip}
        </p>
      )}
    </Panel>
  );
}
