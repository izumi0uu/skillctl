import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { descriptorToCatalogSkill } from "../src/catalog.js";
import { hashDirectory } from "../src/hash.js";
import { pruneManaged } from "../src/prune.js";
import { syncCatalog } from "../src/sync.js";
import type { SkillctlCatalog, SkillctlConfig } from "../src/types.js";
import { makeTempDir, writeSkill } from "./helpers.js";

const originalHome = process.env.HOME;

afterEach(() => {
  if (originalHome) {
    process.env.HOME = originalHome;
  }
});

describe("sync and prune", () => {
  test("copies only managed public skills and preserves unmanaged directories", async () => {
    const repoRoot = await makeTempDir("skillctl-sync-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillPath = await writeSkill(skillsDir, "alpha");
    const hash = await hashDirectory(skillPath);
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "local-public",
        hash,
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillPath),
      }],
    };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };

    const codexDir = path.join(fakeHome, ".codex", "skills");
    await fs.mkdir(path.join(codexDir, "manual-skill"), { recursive: true });
    await fs.writeFile(path.join(codexDir, "manual-skill", "SKILL.md"), "---\nname: manual-skill\ndescription: manual\n---\n", "utf8");

    const result = await syncCatalog(repoRoot, config, catalog);
    expect(result.copied).toEqual([{ agent: "codex", skillId: "alpha" }]);
    expect(await fs.readFile(path.join(codexDir, "alpha", "SKILL.md"), "utf8")).toContain("name: alpha");
    expect(await fs.readFile(path.join(codexDir, "manual-skill", "SKILL.md"), "utf8")).toContain("manual-skill");
  });

  test("prune removes only previously managed directories", async () => {
    const repoRoot = await makeTempDir("skillctl-prune-");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;
    const codexDir = path.join(fakeHome, ".codex", "skills");
    await fs.mkdir(path.join(codexDir, "alpha"), { recursive: true });
    await fs.mkdir(path.join(codexDir, "manual-skill"), { recursive: true });
    await fs.writeFile(path.join(codexDir, "alpha", "SKILL.md"), "---\nname: alpha\ndescription: alpha\n---\n", "utf8");
    await fs.writeFile(path.join(codexDir, "manual-skill", "SKILL.md"), "---\nname: manual-skill\ndescription: manual\n---\n", "utf8");
    await fs.mkdir(path.join(repoRoot, ".skillctl-local", "managed"), { recursive: true });
    await fs.writeFile(path.join(repoRoot, ".skillctl-local", "managed", "codex.json"), JSON.stringify({
      version: 1,
      agent: "codex",
      entries: [{ skill_id: "alpha", hash: "abc", managedAt: new Date().toISOString() }],
    }, null, 2));

    const config: SkillctlConfig = {
      sourceRoots: [],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    const catalog: SkillctlCatalog = { version: 1, generatedBy: "test", skills: [] };

    const result = await pruneManaged(repoRoot, config, catalog);
    expect(result.removed).toEqual([{ agent: "codex", skillId: "alpha" }]);
    await expect(fs.access(path.join(codexDir, "alpha"))).rejects.toThrow();
    expect(await fs.readFile(path.join(codexDir, "manual-skill", "SKILL.md"), "utf8")).toContain("manual-skill");
  });
});
