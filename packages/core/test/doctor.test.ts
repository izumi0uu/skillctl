import fs from "node:fs/promises";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { normalizeCatalogArtifacts } from "../src/attribution.js";
import { hashDirectory } from "../src/hash.js";
import { repairCatalog } from "../src/repair.js";
import { runDoctor } from "../src/doctor.js";
import type { SkillctlCatalog, SkillctlConfig } from "../src/types.js";
import { makeTempDir, writeReadme, writeSkill } from "./helpers.js";

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
    await writeReadme(repoRoot, "# skillctl\n");
    const embeddedRepo = path.join(repoRoot, "vercel-skills");
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
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillDir),
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
          local_modifications: false,
        },
      }],
    };
    await normalizeCatalogArtifacts(repoRoot, catalog);

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.exitCode).toBe(1);
    expect(report.issues.some((issue) => issue.code === "drift" || issue.code === "footer-drift")).toBe(true);

    const repaired = await repairCatalog(repoRoot, config, catalog);
    expect(repaired.exitCode).toBe(0);
  });

  test("warns when embedded upstream repo is present but not bootstrapped", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-transport-");
    const embeddedRepo = path.join(repoRoot, "vercel-skills");
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

  test("warns on missing provenance and README drift", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-readme-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillDir = await writeSkill(skillsDir, "alpha", "hello");
    await writeReadme(repoRoot, "# skillctl\n\nstale\n");

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
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: await hashDirectory(skillDir),
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillDir),
        upstream: {
          repo: "owner/repo",
          sourceType: "github",
        },
      }],
    };

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.issues.some((issue) => issue.code === "missing-provenance")).toBe(true);
    expect(report.issues.some((issue) => issue.code === "readme-drift")).toBe(true);
  });

  test("advisory warnings do not fail doctor when no repairable issue exists", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-advisory-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillDir = await writeSkill(skillsDir, "alpha", "hello");
    await writeReadme(repoRoot, "# skillctl\n");

    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: [],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: await hashDirectory(skillDir),
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillDir),
        upstream: {
          repo: "owner/repo",
          sourceType: "github",
        },
      }],
    };

    await normalizeCatalogArtifacts(repoRoot, catalog);

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.healthy).toBe(true);
    expect(report.exitCode).toBe(0);
    expect(report.issues).toEqual([
      expect.objectContaining({
        code: "missing-provenance",
        status: "warn",
        repairable: false,
      }),
    ]);
  });

  test("reports portability classification and warns on needs-review", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-portability-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillDir = path.join(skillsDir, "alpha");
    await fs.mkdir(skillDir, { recursive: true });
    await fs.writeFile(path.join(skillDir, "SKILL.md"), "---\nname: alpha\n---\n\n# alpha\n", "utf8");
    await writeReadme(repoRoot, "# skillctl\n");

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
        origin_kind: "local-authored",
        hash: await hashDirectory(skillDir),
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillDir),
      }],
    };

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.portability.find((entry) => entry.skillId === "alpha")?.classification).toBe("needs-review");
    expect(report.issues.some((issue) => issue.code === "portability-review")).toBe(true);
  });

  test("does not report drift when claude-only skill is intentionally not installed for codex", async () => {
    const repoRoot = await makeTempDir("skillctl-doctor-portability-gated-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillDir = await writeSkill(skillsDir, "alpha", "!`echo hello`");
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

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
        origin_kind: "local-authored",
        hash: await hashDirectory(skillDir),
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillDir),
      }],
    };

    const report = await runDoctor(repoRoot, config, catalog);
    expect(report.portability.find((entry) => entry.skillId === "alpha")?.classification).toBe("claude-only");
    expect(report.issues.some((issue) => issue.code === "drift")).toBe(false);
  });
});
