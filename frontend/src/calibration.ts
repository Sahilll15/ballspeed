// Vertical plane through both middle stumps: x along the pitch, y up (metres).
export const CALIB_TARGETS = [
  { label: 'bowler_stump_base', name: "Bowler's stumps, base", world: { x: 0, y: 0 } },
  { label: 'bowler_stump_top', name: "Bowler's stumps, top", world: { x: 0, y: 0.711 } },
  { label: 'batter_stump_base', name: "Batter's stumps, base", world: { x: 20.12, y: 0 } },
  { label: 'batter_stump_top', name: "Batter's stumps, top", world: { x: 20.12, y: 0.711 } },
] as const
