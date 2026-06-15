import type { DiffChange } from "./ipc-contract";

// Compare two skill sets by hash to produce a pending-change list.
export function diffSkillHashes(
  prev: ReadonlyArray<{ skill_id: string; hash: string }>,
  next: ReadonlyArray<{ skill_id: string; hash: string }>,
): DiffChange[] {
  const oldMap = new Map(prev.map((skill) => [skill.skill_id, skill.hash]));
  const newMap = new Map(next.map((skill) => [skill.skill_id, skill.hash]));
  const changes: DiffChange[] = [];
  for (const [id, hash] of newMap) {
    const previous = oldMap.get(id);
    if (previous === undefined) {
      changes.push({ skill: id, kind: "added" });
    } else if (previous !== hash) {
      changes.push({ skill: id, kind: "changed" });
    }
  }
  for (const [id] of oldMap) {
    if (!newMap.has(id)) {
      changes.push({ skill: id, kind: "removed" });
    }
  }
  return changes;
}
