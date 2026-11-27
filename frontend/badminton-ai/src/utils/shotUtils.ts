export const SHOT_COLORS: Record<string, string> = {
  Clear:   "#89c2d9",
  Drive:   "#f4a261",
  Drop:    "#a8dadc",
  Lob:     "#e9c46a",
  Net:     "#b7e4c7",
  Smash:   "#e63946",
  Unknown: "#6c757d",
};

export function shotColor(type: string): string {
  return SHOT_COLORS[type] ?? SHOT_COLORS.Unknown;
}

/**
 * Shot-group colours for the match library: the same map extended with the
 * groups the analysis view doesn't have. Lift takes Lob's colour (a lob is a lift);
 * Block is a darker shade of Net's green (a block is played short, like a net shot).
 */
export const GROUP_COLORS: Record<string, string> = {
  ...SHOT_COLORS,
  Lift:  SHOT_COLORS.Lob,
  Block: "#52b788",
  Push:  "#cdb4db",
  Serve: "#d6d3d1",
};

export function groupColor(group: string): string {
  return GROUP_COLORS[group] ?? GROUP_COLORS.Unknown;
}
