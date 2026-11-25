import { groupColor } from "@/utils/shotUtils";
import type { ShotDoc } from "../types";

/** Legend order on the match page. */
export const LEGEND_GROUPS = ["Serve", "Smash", "Clear", "Drop", "Net", "Lift", "Drive", "Push"] as const;

/** Display label for a shot: serves have no group; an unclassified shot is "Unknown". */
export function shotLabel(shot: ShotDoc): string {
  if (shot.s) return "Serve";
  return shot.g ?? "Unknown";
}

export function shotFill(label: string): string {
  return groupColor(label);
}

/** Chip text colour: dark on the pastel fills, light on the grey Unknown fill. */
export function shotInk(label: string): string {
  return label === "Unknown" ? "#FAFAF9" : "#0A0A0A";
}
