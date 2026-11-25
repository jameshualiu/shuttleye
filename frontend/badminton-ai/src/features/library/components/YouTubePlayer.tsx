import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";

type YTPlayer = {
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  getIframe(): HTMLIFrameElement;
  destroy(): void;
};

type YTNamespace = {
  Player: new (
    el: HTMLElement,
    options: {
      videoId: string;
      host?: string;
      playerVars?: Record<string, number | string>;
      events?: { onReady?: () => void };
    },
  ) => YTPlayer;
};

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

// The IFrame API script is loaded once per page load and shared by every player.
let apiPromise: Promise<YTNamespace> | null = null;

function loadYouTubeApi(): Promise<YTNamespace> {
  if (apiPromise) return apiPromise;
  apiPromise = new Promise<YTNamespace>((resolve, reject) => {
    if (window.YT?.Player) {
      resolve(window.YT);
      return;
    }
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT) resolve(window.YT);
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.async = true;
    script.onerror = () => {
      apiPromise = null; // let a later mount retry
      script.remove();
      reject(new Error("YouTube player failed to load"));
    };
    document.head.appendChild(script);
  });
  return apiPromise;
}

/** Seconds of lead-in before a seek target, so the moment isn't cut off. */
const LEAD_IN_SEC = 1;

export type YouTubePlayerHandle = {
  /** Jump to `sec` (minus a 1 s lead-in, never below 0) and play. */
  seekTo(sec: number): void;
};

type YouTubePlayerProps = {
  videoId: string;
  title: string;
  className?: string;
  ref?: Ref<YouTubePlayerHandle>;
};

export function YouTubePlayer({ videoId, title, className, ref }: YouTubePlayerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const readyRef = useRef(false);
  const pendingRef = useRef<number | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let player: YTPlayer | null = null;
    const host = hostRef.current;
    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !host) return;
        // The API replaces this element with its iframe; React never renders into it.
        const mount = document.createElement("div");
        host.appendChild(mount);
        player = new YT.Player(mount, {
          videoId,
          host: "https://www.youtube-nocookie.com",
          playerVars: { rel: 0, playsinline: 1 },
          events: {
            onReady: () => {
              if (cancelled || !player) return;
              readyRef.current = true;
              player.getIframe().title = title;
              if (pendingRef.current !== null) {
                player.seekTo(pendingRef.current, true);
                player.playVideo();
                pendingRef.current = null;
              }
            },
          },
        });
        playerRef.current = player;
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      readyRef.current = false;
      playerRef.current = null;
      player?.destroy();
      host?.replaceChildren();
    };
  }, [videoId, title]);

  useImperativeHandle(
    ref,
    () => ({
      seekTo(sec: number) {
        const target = Math.max(0, sec - LEAD_IN_SEC);
        const player = playerRef.current;
        if (player && readyRef.current) {
          player.seekTo(target, true);
          player.playVideo();
        } else {
          pendingRef.current = target;
        }
      },
    }),
    [],
  );

  return (
    <div className={className}>
      <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-video-canvas">
        <div ref={hostRef} className="absolute inset-0 [&>iframe]:size-full" />
        {failed && (
          <p className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-neutral-300">
            The YouTube player didn't load. Check your connection and reload the page.
          </p>
        )}
      </div>
    </div>
  );
}
