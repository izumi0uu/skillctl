import { describe, expect, test } from "vitest";

import { diffSkillHashes } from "./skill-diff";

describe("diffSkillHashes", () => {
  test("detects added, removed, and changed skills", () => {
    const prev = [
      { skill_id: "a", hash: "1" },
      { skill_id: "b", hash: "1" },
    ];
    const next = [
      { skill_id: "a", hash: "2" },
      { skill_id: "c", hash: "1" },
    ];
    const changes = diffSkillHashes(prev, next);
    expect(changes).toContainEqual({ skill: "a", kind: "changed" });
    expect(changes).toContainEqual({ skill: "c", kind: "added" });
    expect(changes).toContainEqual({ skill: "b", kind: "removed" });
    expect(changes).toHaveLength(3);
  });

  test("is empty when nothing changed", () => {
    const same = [{ skill_id: "a", hash: "1" }];
    expect(diffSkillHashes(same, same)).toEqual([]);
  });
});
