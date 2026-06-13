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
    const embeddedRepo = path.join(repoRoot, "vendor", "vercel-skills");
    await fs.mkdir(path.join(embeddedRepo, "src"), { recursive: true });
    await fs.writeFile(path.join(embeddedRepo, "package.json"), JSON.stringify({ name: "skills" }), "utf8");
    await fs.writeFile(path.join(embeddedRepo, "src", "cli.ts"), "console.log('skills');\n", "utf8");
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
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
        embeddedRepoPath: embeddedRepo,
      },
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

  test("warns when embedded upstream repo is present but not bootstrapped", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-transport-");
    const embeddedRepo = path.join(repoRoot, "vendor", "vercel-skills");
    await fs.mkdir(path.join(embeddedRepo, "src"), { recursive: true });
    await fs.writeFile(path.join(embeddedRepo, "package.json"), JSON.stringify({ name: "skills" }), "utf8");
    await fs.writeFile(path.join(embeddedRepo, "src", "cli.ts"), "console.log('skills');\n", "utf8");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    const config: SkillctlConfig = {
      sourceRoots: [],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "skills-cli",
        command: "npx",
        args: ["--yes", "skills"],
        embeddedRepoPath: embeddedRepo,
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    const catalog: SkillctlCatalog = { version: 1, generatedBy: "test", skills: [] };

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.exitCode).toBe(1);
    expect(report.issues.some((issue) => issue.code === "transport-not-ready")).toBe(true);
  });
});
