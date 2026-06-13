import fs from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { adoptSkill } from "../src/adopt.js";
import type { SkillctlCatalog, SkillctlConfig } from "../src/types.js";
import { makeTempDir, writeReadme, writeSkill } from "./helpers.js";

describe("adoptSkill", () => {
  test("adopts a skill with explicit upstream provenance", async () => {
    const repoRoot = await makeTempDir("skillctl-adopt-");
    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await writeReadme(repoRoot, "# skillctl\n");
    const externalRoot = await makeTempDir("skillctl-source-");
    const sourceDir = await writeSkill(externalRoot, "alpha", "body");

    const catalog: SkillctlCatalog = { version: 1, generatedBy: "test", skills: [] };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: path.join(repoRoot, "skills"), visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: { mode: "copy-fallback", command: "npx", args: ["--yes", "skills"] },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };

    const result = await adoptSkill(repoRoot, config, catalog, {
      sourcePath: sourceDir,
      fromRepo: "owner/repo",
      skillPath: "skills/alpha",
      ref: "main",
      sourceType: "github",
    });

    expect(result.skill.origin_kind).toBe("imported-upstream");
    expect(result.skill.upstream?.repo).toBe("owner/repo");
    expect(await fs.readFile(path.join(result.destinationDir, "SKILL.md"), "utf8")).toContain("## Source Attribution");
  });

  test("adopts a self-authored skill without fake provenance", async () => {
    const repoRoot = await makeTempDir("skillctl-adopt-");
    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await writeReadme(repoRoot, "# skillctl\n");
    const sourceRoot = await makeTempDir("skillctl-source-");
    const sourceDir = await writeSkill(sourceRoot, "beta", "body");

    const catalog: SkillctlCatalog = { version: 1, generatedBy: "test", skills: [] };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: path.join(repoRoot, "skills"), visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: { mode: "copy-fallback", command: "npx", args: ["--yes", "skills"] },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };

    const result = await adoptSkill(repoRoot, config, catalog, {
      sourcePath: sourceDir,
    });

    expect(result.skill.origin_kind).toBe("local-authored");
    expect(result.skill.upstream).toBeUndefined();
    expect(await fs.readFile(path.join(result.destinationDir, "SKILL.md"), "utf8")).not.toContain("## Source Attribution");
  });
});
