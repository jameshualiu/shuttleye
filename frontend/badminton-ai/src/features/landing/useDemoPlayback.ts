import { useEffect, useState, type RefObject } from "react";
import { useReducedMotion } from "motion/react";

// Plays the demo video only while it's onscreen and the tab is visible, and
// never autoplays under prefers-reduced-motion: the poster stays up until
// `start` is called from a user action (the play button or a rally click).
// `container` is an element (from a callback ref) so the observer attaches
// once it mounts. `videoMounted` must flip to true once the <video> exists:
// the container can scroll into view while the analysis is still loading, and
// the play effect has to re-run when the video appears.
export function useDemoPlayback(
  videoRef: RefObject<HTMLVideoElement | null>,
  container: HTMLElement | null,
  videoMounted: boolean,
) {
  const reduceMotion = useReducedMotion();
  const [started, setStarted] = useState(false);
  const [inView, setInView] = useState(false);
  const [tabVisible, setTabVisible] = useState(
    () => typeof document === "undefined" || document.visibilityState === "visible",
  );

  useEffect(() => {
    if (!container) return;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting));
    io.observe(container);
    return () => io.disconnect();
  }, [container]);

  useEffect(() => {
    const onChange = () => setTabVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);

  const mayPlay = !reduceMotion || started;
  const shouldPlay = mayPlay && inView && tabVisible;

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (shouldPlay) v.play().catch(() => {});
    else v.pause();
  }, [videoRef, shouldPlay, videoMounted]);

  return { showPlayButton: !!reduceMotion && !started, start: () => setStarted(true) };
}
