import fs from "node:fs/promises";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { hashDirectory } from "../src/hash.js";
import { repairCatalog } from "../src/repair.js";
import { runDoctor } from "../src/doctor.js";
import type { SkillctlCatalog, SkillctlConfig } from "../src/types.js";
import { makeTempDir, writeSkill } from "./helpers.js";

const originalHome = process.env.HOME;

afterEach(() => {
  if (originalHome) {
    process.env.HOME = originalHome;
  }
});

describe("doctor and repair", () => {
  test("detects drift and repair restores managed skill", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillDir = await writeSkill(skillsDir, "alpha", "hello");
    const hash = await hashDirectory(skillDir);
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;
    const codexSkillDir = path.join(fakeHome, ".codex", "skills", "alpha");
    await fs.mkdir(codexSkillDir, { recursive: true });
    await fs.writeFile(path.join(codexSkillDir, "SKILL.md"), "---\nname: alpha\ndescription: changed\n---\n", "utf8");

    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
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
        canonical_rel_path: path.relative(repoRoot, skillDir),
      }],
    };

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.exitCode).toBe(1);
    expect(report.issues.some((issue) => issue.code === "drift")).toBe(true);

    const repaired = await repairCatalog(repoRoot, config, catalog);
    expect(repaired.exitCode).toBe(0);
  });
});
