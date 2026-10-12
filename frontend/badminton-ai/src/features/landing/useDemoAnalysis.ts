import { useEffect, useState } from "react";
import type { AnalysisData } from "../analysis/types";
import { analysisFps, demoClipFromEnv, fetchDemoAnalysis, type DemoClip } from "./demoClip";

export type DemoState =
  | { status: "loading" }
  | { status: "unavailable" }
  | {
      status: "ready";
      clip: DemoClip;
      data: AnalysisData;
      fps: number;
      durationSec: number;
      // width / height of the analysed video, for sizing the overlay stage.
      aspectRatio: number | undefined;
      // Where the first playthrough starts: just before the first shot, so
      // visitors don't sit through the lead-in. Loops restart from 0.
      startSec: number;
    };

const LEAD_IN_SEC = 2;

// Loads the demo clip's analysis.json at runtime. No Firebase or backend calls.
export function useDemoAnalysis(): DemoState {
  const [clip] = useState(demoClipFromEnv);
  const [state, setState] = useState<DemoState>(() =>
    clip ? { status: "loading" } : { status: "unavailable" },
  );

  useEffect(() => {
    if (!clip) return;
    const ctrl = new AbortController();
    fetchDemoAnalysis(clip.analysisUrl, ctrl.signal).then((result) => {
      if (ctrl.signal.aborted) return;
      if (!result.ok) {
        setState({ status: "unavailable" });
        return;
      }
      const data = result.value;
      const res = data.summary?.resolution;
      const fps = analysisFps(data);
      const firstFrame = Math.min(...data.events.map((e) => e.frame));
      setState({
        status: "ready",
        clip,
        data,
        fps,
        durationSec: data.summary?.durationSec ?? 0,
        aspectRatio: res ? res[0] / res[1] : undefined,
        startSec: Number.isFinite(firstFrame) ? Math.max(0, firstFrame / fps - LEAD_IN_SEC) : 0,
      });
    });
    return () => ctrl.abort();
  }, [clip]);

  return state;
}
