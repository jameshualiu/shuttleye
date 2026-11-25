import { Timestamp } from "firebase/firestore";
import type { VideoStatus } from "./videoService";
export type { VideoStatus };

export interface DashboardVideoCard {
    id: string;
    title: string;
    createdAt?: Timestamp;
    date: string; // ISO string for convenience
    thumbnail?: string | null; // optional for now
    duration?: number | null; // seconds
    totalShots?: number | null;
    status?: VideoStatus;
}

// Product shot types. "Serve" only comes from the full-match analyzer;
// "Unknown" when no classifier could decide. Other strings are tolerated
// because older payloads used ad hoc labels.
export type ShotType = "Clear" | "Smash" | "Drop" | "Drive" | "Net" | "Lob" | "Serve" | "Unknown";

export interface AnalysisShot {
    frame: number;
    location_px: [number, number] | null;
    location_m: [number, number] | null;
    type: ShotType | (string & {});
    // Optional because the upload path may omit them. In the full-match result
    // (data-flow.md, "Full-match result") timeSec, isServe, side,
    // sideOverridden and detailType are always present; typeConfidence,
    // confidence, confirmed and source can be missing (e.g. on inserted serves).
    timeSec?: number;              // frame / fps, full-video seconds
    isServe?: boolean;
    side?: "Top" | "Bottom" | null; // Top = far end, Bottom = near end
    sideOverridden?: boolean;      // side decode overrode strong evidence
    detailType?: string | null;    // ShuttleSet 10-class name, e.g. "net shot" (BST-0 on both paths)
    typeConfidence?: number;
    confidence?: number | null;    // hit detector confidence (null on inserted serves)
    confirmed?: boolean;
    source?: string;               // e.g. "hitnet", "serve_onset"
}

// Full-match result only: one rally, frames in full-video space.
export interface AnalysisRally {
    id: number;
    set: number | null;
    startFrame: number;
    endFrame: number;
    startSec: number;
    endSec: number;
    eventIndices: number[];              // indices into events
    scoreAfter: [number, number] | null; // [A, B], A = the match winner
    winner: "A" | "B" | null;
    nearPlayer: "A" | "B" | null;
    scoreRead: boolean;
}

export interface AnalysisSet {
    set: number;
    nearPlayer: "A" | "B" | null;        // at the start of the set
    finalScore: [number, number] | null; // [A, B]
}

export interface TrackingPlayer {
    id: number;
    skeleton: ([number, number] | null)[];
    box: [number, number, number, number];
}

export interface TrackingFrame {
    frame: number;
    players: TrackingPlayer[];
}

export interface AnalysisData {
    // Optional: the worker's ML output is best-effort and a malformed/partial
    // payload can omit this entirely. Every consumer must guard it (FE-09).
    summary?: {
        durationSec: number | null;      // null only in a full-match result built without totalFrames
        totalShots: number;
        shotCounts: Record<string, number>;
        resolution?: [number, number];   // always set by the upload path; full match: when known
        truncated?: boolean;
        rallyCount?: number;   // full-match result only
        serveCount?: number;   // full-match result only
    };
    // geometry and tracking are always set by the upload path and absent from
    // the full-match result.
    geometry?: {
        court: [number, number][] | null;
        net: [number, number][] | null;
        court_keypoints_6: [number, number][] | null;   // [TL, TR, ML, MR, BL, BR]
        court_keypoints_35: [number, number][] | null;  // 7 rows x 5 cols expanded grid
    } | null;
    events: AnalysisShot[];
    tracking?: TrackingFrame[];
    shuttle_debug?: { frame: number; pos: [number, number] | null; confidence: number }[];
    // Full-match result only (always present there). It has no geometry or
    // tracking, so the current analysis page does not render it yet.
    fps?: number;
    totalFrames?: number | null;
    court?: [number, number][] | null;   // match-wide 6-point court, pipeline px
    rallies?: AnalysisRally[];
    sets?: AnalysisSet[];
    timings?: Record<string, number | (number | null)[] | null>;
    skippedSteps?: { step: string; error: string }[];   // optional steps / chunks ("chunk <id>") that failed
    models?: AnalysisModels;
    warnings?: string[];   // e.g. a source that is not 30 fps; [] when none
}

// Full-match result only: what actually ran (null = did not run / not known).
export interface AnalysisModels {
    strokes: string | null;              // stroke classifier the chunks loaded, e.g. "BST0Adapter"
    shotStack: string | null;            // stacked classifier model path
    scoreboardTemplates: string | null;  // score-graphic digit templates path
}
