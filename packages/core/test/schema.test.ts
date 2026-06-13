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
        origin_kind: "local-authored",
        hash: "abc",
        managed: true,
        targets: ["codex"],
      }],
    });
    expect(parsed.skills[0]?.skill_id).toBe("demo");
  });

  test("accepts upstream provenance metadata", () => {
    const parsed = skillctlCatalogSchema.parse({
      version: 1,
      generatedBy: "skillctl",
      skills: [{
        skill_id: "demo",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "abc",
        managed: true,
        targets: ["codex"],
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/demo",
          sourceType: "github",
          imported_at: "2026-06-13T00:00:00.000Z",
          last_verified_ref: "main",
          local_modifications: false,
        },
      }],
    });
    expect(parsed.skills[0]?.upstream?.repo).toBe("owner/repo");
  });
});
