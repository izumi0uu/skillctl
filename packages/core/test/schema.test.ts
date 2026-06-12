import { describe, expect, test } from "vitest";

import { skillctlCatalogSchema, skillctlConfigSchema } from "../src/schema.js";

describe("schema", () => {
  test("accepts valid config", () => {
    const parsed = skillctlConfigSchema.parse({
      sourceRoots: [{ path: "./skills", visibility: "public" }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
    });
    expect(parsed.enabledAdapters).toEqual(["codex"]);
  });

  test("rejects invalid adapter", () => {
    expect(() => skillctlConfigSchema.parse({
      sourceRoots: [{ path: "./skills", visibility: "public" }],
      privateRoots: [],
      enabledAdapters: ["cursor"],
      excludeSkills: [],
      liveProbePolicy: "off",
    })).toThrow();
  });

  test("accepts valid catalog", () => {
    const parsed = skillctlCatalogSchema.parse({
      version: 1,
      generatedBy: "skillctl",
      skills: [{
        skill_id: "demo",
        visibility: "public",
        source_kind: "local-public",
        hash: "abc",
        managed: true,
        targets: ["codex"],
      }],
    });
    expect(parsed.skills[0]?.skill_id).toBe("demo");
  });
});
