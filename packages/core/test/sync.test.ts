import fs from "node:fs/promises";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { normalizeCatalogArtifacts } from "../src/attribution.js";
import { hashDirectory } from "../src/hash.js";
import { pruneManaged } from "../src/prune.js";
import { syncCatalog } from "../src/sync.js";
import type { SkillctlCatalog, SkillctlConfig } from "../src/types.js";
import { makeTempDir, writeReadme, writeSkill } from "./helpers.js";

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
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

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
        canonical_rel_path: path.relative(repoRoot, skillPath),
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
          local_modifications: false,
        },
      }],
    };
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
    await normalizeCatalogArtifacts(repoRoot, catalog);

    const codexDir = path.join(fakeHome, ".codex", "skills");
    await fs.mkdir(path.join(codexDir, "manual-skill"), { recursive: true });
    await fs.writeFile(path.join(codexDir, "manual-skill", "SKILL.md"), "---\nname: manual-skill\ndescription: manual\n---\n", "utf8");

    const result = await syncCatalog(repoRoot, config, catalog);
    expect(result.copied).toEqual([{ agent: "codex", skillId: "alpha" }]);
    expect(await fs.readFile(path.join(codexDir, "alpha", "SKILL.md"), "utf8")).toContain("name: alpha");
    expect(await fs.readFile(path.join(codexDir, "alpha", "SKILL.md"), "utf8")).toContain("## Source Attribution");
    expect(await fs.readFile(path.join(codexDir, "manual-skill", "SKILL.md"), "utf8")).toContain("manual-skill");
    expect(await fs.readFile(path.join(repoRoot, "README.md"), "utf8")).toContain("Managed Skill Sources");
  });

  test("normalizes excluded runtime artifacts out of sync health", async () => {
    const repoRoot = await makeTempDir("skillctl-sync-portable-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillPath = await writeSkill(skillsDir, "portable");
    await fs.mkdir(path.join(skillPath, ".venv", "bin"), { recursive: true });
    await fs.mkdir(path.join(skillPath, "__pycache__"), { recursive: true });
    await fs.writeFile(path.join(skillPath, ".venv", "bin", "python"), "python", "utf8");
    await fs.writeFile(path.join(skillPath, "__pycache__", "skill.pyc"), "compiled", "utf8");
    await fs.writeFile(path.join(skillPath, "metadata.json"), "{\"private\":true}\n", "utf8");
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "portable",
        visibility: "public",
        source_kind: "local-public",
        origin_kind: "local-authored",
        hash: "placeholder",
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
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };

    await normalizeCatalogArtifacts(repoRoot, catalog);
    await syncCatalog(repoRoot, config, catalog);

    const installedDir = path.join(fakeHome, ".codex", "skills", "portable");
    expect(await hashDirectory(installedDir)).toBe(catalog.skills[0]?.hash);
    await expect(fs.access(path.join(installedDir, ".venv"))).rejects.toThrow();
    await expect(fs.access(path.join(installedDir, "__pycache__"))).rejects.toThrow();
    await expect(fs.access(path.join(installedDir, "metadata.json"))).rejects.toThrow();
  });

  test("skills-cli transport footers the final per-agent install after mirroring", async () => {
    const repoRoot = await makeTempDir("skillctl-sync-cli-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillPath = await writeSkill(skillsDir, "alpha");
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    // Stand in for the upstream skills CLI in copy mode for a universal agent:
    // it installs into the canonical ~/.agents/skills, NOT the adapter dir. The
    // source is intentionally left un-footered so this only passes if skillctl
    // applies attribution AFTER mirroring into ~/.codex/skills.
    const fakeCli = path.join(repoRoot, "fake-skills.mjs");
    await fs.writeFile(
      fakeCli,
      [
        'import { cpSync, mkdirSync, rmSync } from "node:fs";',
        'import os from "node:os";',
        'import path from "node:path";',
        'const args = process.argv.slice(2);',
        'const sourceDir = args[args.indexOf("add") + 1];',
        'const sIndex = args.indexOf("-s");',
        'const skillId = sIndex !== -1 ? args[sIndex + 1] : path.basename(sourceDir);',
        'const dest = path.join(os.homedir(), ".agents", "skills", skillId);',
        'rmSync(dest, { recursive: true, force: true });',
        'mkdirSync(path.dirname(dest), { recursive: true });',
        'cpSync(sourceDir, dest, { recursive: true });',
        "",
      ].join("\n"),
      "utf8",
    );

    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "local-public",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: path.relative(repoRoot, skillPath),
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
          local_modifications: false,
        },
      }],
    };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "skills-cli",
        command: "node",
        args: [fakeCli],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };

    const result = await syncCatalog(repoRoot, config, catalog);

    expect(result.copied).toContainEqual({ agent: "codex", skillId: "alpha" });
    const installed = await fs.readFile(path.join(fakeHome, ".codex", "skills", "alpha", "SKILL.md"), "utf8");
    expect(installed).toContain("## Source Attribution");
    expect(installed).toContain("imported-upstream");
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
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    const catalog: SkillctlCatalog = { version: 1, generatedBy: "test", skills: [] };

    const result = await pruneManaged(repoRoot, config, catalog);
    expect(result.removed).toEqual([{ agent: "codex", skillId: "alpha" }]);
    await expect(fs.access(path.join(codexDir, "alpha"))).rejects.toThrow();
    expect(await fs.readFile(path.join(codexDir, "manual-skill", "SKILL.md"), "utf8")).toContain("manual-skill");
  });

  test("claude-only skills are blocked from codex by default in copy fallback", async () => {
    const repoRoot = await makeTempDir("skillctl-sync-claude-only-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillPath = await writeSkill(skillsDir, "alpha", "!`echo hello`");
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "local-public",
        origin_kind: "local-authored",
        hash: "placeholder",
        managed: true,
        targets: ["claude-code", "codex"],
        canonical_rel_path: path.relative(repoRoot, skillPath),
      }],
    };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["claude-code", "codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    await normalizeCatalogArtifacts(repoRoot, catalog);

    const result = await syncCatalog(repoRoot, config, catalog);
    expect(result.copied).toContainEqual({ agent: "claude-code", skillId: "alpha" });
    expect(result.skipped).toContainEqual({
      agent: "codex",
      skillId: "alpha",
      reason: "blocked by claude-only portability policy",
    });
    await expect(fs.access(path.join(fakeHome, ".codex", "skills", "alpha"))).rejects.toThrow();
    expect(await fs.readFile(path.join(fakeHome, ".claude", "skills", "alpha", "SKILL.md"), "utf8")).toContain("name: alpha");
  });

  test("portability override can allow codex distribution for claude-only skill", async () => {
    const repoRoot = await makeTempDir("skillctl-sync-override-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillPath = await writeSkill(skillsDir, "alpha", "!`echo hello`");
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "local-public",
        origin_kind: "local-authored",
        hash: "placeholder",
        managed: true,
        targets: ["claude-code", "codex"],
        canonical_rel_path: path.relative(repoRoot, skillPath),
        distribution: {
          portability_allow_targets: ["codex"],
        },
      }],
    };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["claude-code", "codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    await normalizeCatalogArtifacts(repoRoot, catalog);

    const result = await syncCatalog(repoRoot, config, catalog);
    expect(result.copied).toContainEqual({ agent: "codex", skillId: "alpha" });
    expect(await fs.readFile(path.join(fakeHome, ".codex", "skills", "alpha", "SKILL.md"), "utf8")).toContain("name: alpha");
  });

  test("skills-cli removes blocked final-agent install and keeps sync successful", async () => {
    const repoRoot = await makeTempDir("skillctl-sync-cli-blocked-");
    const skillsDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillsDir, { recursive: true });
    const skillPath = await writeSkill(skillsDir, "alpha", "!`echo hello`");
    await writeReadme(repoRoot, "# skillctl\n");
    const fakeHome = await makeTempDir("skillctl-home-");
    process.env.HOME = fakeHome;

    await fs.mkdir(path.join(fakeHome, ".codex", "skills", "alpha"), { recursive: true });
    await fs.writeFile(path.join(fakeHome, ".codex", "skills", "alpha", "SKILL.md"), "---\nname: alpha\ndescription: stale\n---\n", "utf8");

    const fakeCli = path.join(repoRoot, "fake-skills.mjs");
    await fs.writeFile(
      fakeCli,
      [
        'import { cpSync, mkdirSync, rmSync } from "node:fs";',
        'import os from "node:os";',
        'import path from "node:path";',
        'const args = process.argv.slice(2);',
        'const sourceDir = args[args.indexOf("add") + 1];',
        'const sIndex = args.indexOf("-s");',
        'const skillId = sIndex !== -1 ? args[sIndex + 1] : path.basename(sourceDir);',
        'const dest = path.join(os.homedir(), ".agents", "skills", skillId);',
        'rmSync(dest, { recursive: true, force: true });',
        'mkdirSync(path.dirname(dest), { recursive: true });',
        'cpSync(sourceDir, dest, { recursive: true });',
        "",
      ].join("\n"),
      "utf8",
    );

    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "local-public",
        origin_kind: "local-authored",
        hash: "placeholder",
        managed: true,
        targets: ["claude-code", "codex"],
        canonical_rel_path: path.relative(repoRoot, skillPath),
      }],
    };
    const config: SkillctlConfig = {
      sourceRoots: [{ path: skillsDir, visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["claude-code", "codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "skills-cli",
        command: "node",
        args: [fakeCli],
      },
      stateDir: path.join(repoRoot, ".skillctl-local"),
    };
    await normalizeCatalogArtifacts(repoRoot, catalog);

    const result = await syncCatalog(repoRoot, config, catalog);
    expect(result.skipped).toContainEqual({
      agent: "codex",
      skillId: "alpha",
      reason: "blocked by claude-only portability policy",
    });
    await expect(fs.access(path.join(fakeHome, ".codex", "skills", "alpha"))).rejects.toThrow();
    expect(await fs.readFile(path.join(fakeHome, ".claude", "skills", "alpha", "SKILL.md"), "utf8")).toContain("name: alpha");
  });
});
