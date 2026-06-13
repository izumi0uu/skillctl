import fs from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { discoverCatalog } from "../src/discover.js";
import { makeTempDir, writeSkill } from "./helpers.js";

describe("discoverCatalog", () => {
  test("builds catalog from public root", async () => {
    const repoRoot = await makeTempDir("skillctl-discover-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    await writeSkill(skillsDir, "alpha");

    const result = await discoverCatalog(repoRoot, {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      stateDir: path.join(repoRoot, ".skillctl-local"),
    });

    expect(result.conflicts).toEqual([]);
    expect(result.catalog.skills).toHaveLength(1);
    expect(result.catalog.skills[0]?.skill_id).toBe("alpha");
    expect(result.catalog.skills[0]?.origin_kind).toBe("local-authored");
  });

  test("reports duplicate skill ids across roots", async () => {
    const repoRoot = await makeTempDir("skillctl-discover-");
    const publicDir = path.join(repoRoot, "skills");
    const privateDir = path.join(repoRoot, "private-skills");
    await fs.mkdir(publicDir, { recursive: true });
    await fs.mkdir(privateDir, { recursive: true });
    await writeSkill(publicDir, "alpha");
    await writeSkill(privateDir, "alpha");

    const result = await discoverCatalog(repoRoot, {
      sourceRoots: [
        { path: publicDir, visibility: "public", managedByDefault: true },
        { path: privateDir, visibility: "private", managedByDefault: true },
      ],
      privateRoots: [privateDir],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      stateDir: path.join(repoRoot, ".skillctl-local"),
    });

    expect(result.catalog.skills).toHaveLength(0);
    expect(result.conflicts).toHaveLength(1);
    expect(result.conflicts[0]?.skillId).toBe("alpha");
  });

  test("preserves existing provenance metadata during rediscovery", async () => {
    const repoRoot = await makeTempDir("skillctl-discover-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const alphaDir = await writeSkill(skillsDir, "alpha");

    const result = await discoverCatalog(repoRoot, {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      stateDir: path.join(repoRoot, ".skillctl-local"),
      transport: { mode: "copy-fallback", command: "npx", args: ["--yes", "skills"] },
    }, {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "old",
        managed: false,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, alphaDir),
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
          local_modifications: false,
        },
      }],
    });

    expect(result.catalog.skills[0]?.origin_kind).toBe("imported-upstream");
    expect(result.catalog.skills[0]?.managed).toBe(false);
    expect(result.catalog.skills[0]?.upstream?.repo).toBe("owner/repo");
  });
});
