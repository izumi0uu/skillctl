// Pure reducer for the Skills page's in-memory toggle staging. `pending` maps
// skillId -> desired enabled. Toggling back to the saved (`actual`) state drops
// the entry so it is no longer counted as a pending change. Never mutates input.
export function applyToggle(
  pending: ReadonlyMap<string, boolean>,
  skillId: string,
  displayedOn: boolean,
  actual: boolean,
): Map<string, boolean> {
  const next = !displayedOn;
  const map = new Map(pending);
  if (next === actual) {
    map.delete(skillId);
  } else {
    map.set(skillId, next);
  }
  return map;
}
