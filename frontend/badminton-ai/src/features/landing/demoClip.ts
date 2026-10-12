import { err, ok, type Result } from "../../lib/result";
import type { AnalysisData } from "../analysis/types";

export interface DemoClip {
  videoUrl: string;
  posterUrl: string | undefined;
  analysisUrl: string;
}

// The demo clip and its analysis.json are hosted outside git and located via
// env vars: local dev points them at public/demo-local/ (gitignored), and a
// deployed build points them at public object-storage URLs. Without them the
// landing page shows no demo.
export function demoClipFromEnv(): DemoClip | null {
  const videoUrl = import.meta.env.VITE_DEMO_VIDEO_URL as string | undefined;
  const analysisUrl = import.meta.env.VITE_DEMO_ANALYSIS_URL as string | undefined;
  if (!videoUrl || !analysisUrl) return null;
  return {
    videoUrl,
    analysisUrl,
    posterUrl: (import.meta.env.VITE_DEMO_POSTER_URL as string | undefined) || undefined,
  };
}

export async function fetchDemoAnalysis(
  url: string,
  signal: AbortSignal,
): Promise<Result<AnalysisData, string>> {
  try {
    const res = await fetch(url, { signal });
    if (!res.ok) return err(`HTTP ${res.status}`);
    const data: unknown = await res.json();
    if (!data || !Array.isArray((data as AnalysisData).events)) return err("Malformed analysis.json");
    return ok(data as AnalysisData);
  } catch (e) {
    return err(e instanceof Error ? e.message : "Failed to load demo analysis");
  }
}

// analysis.json has no fps field, so derive it the way AnalysisPage does:
// last analysed frame over clip duration.
export function analysisFps(data: AnalysisData): number {
  const dur = data.summary?.durationSec ?? 0;
  const maxFrame = Math.max(
    ...(data.shuttle_debug?.map((s) => s.frame) ?? [0]),
    ...(data.tracking?.map((t) => t.frame) ?? [0]),
  );
  return dur > 0 && maxFrame > 0 ? maxFrame / dur : 30;
}
