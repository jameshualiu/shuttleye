import type { AnalysisShot } from "./types";

export const RALLY_GAP_SEC = 5;

// Group shot events into rallies (gap > RALLY_GAP_SEC between shots = new rally).
export function groupRallies(events: AnalysisShot[], fps: number): AnalysisShot[][] {
  if (!events.length) return [];
  const sorted = [...events].sort((a, b) => a.frame - b.frame);
  const groups: AnalysisShot[][] = [];
  let current: AnalysisShot[] = [sorted[0]];
  for (let i = 1; i < sorted.length; i++) {
    const gapSec = (sorted[i].frame - sorted[i - 1].frame) / fps;
    if (gapSec > RALLY_GAP_SEC) {
      groups.push(current);
      current = [];
    }
    current.push(sorted[i]);
  }
  groups.push(current);
  return groups.sort((a, b) => b.length - a.length); // longest first
}
