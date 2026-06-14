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
    expect(result.skill.source_kind).toBe("upstream");
    expect(result.skill.upstream?.repo).toBe("owner/repo");
    expect(result.skill.canonical_rel_path).toBe("skills/alpha");
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

  test("upgrades an existing local-authored skill to upstream provenance on re-adopt", async () => {
    const repoRoot = await makeTempDir("skillctl-adopt-");
    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await writeReadme(repoRoot, "# skillctl\n");
    const sourceRoot = await makeTempDir("skillctl-source-");
    const sourceDir = await writeSkill(sourceRoot, "delta", "body");

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

    await adoptSkill(repoRoot, config, catalog, {
      sourcePath: sourceDir,
    });

    const result = await adoptSkill(repoRoot, config, catalog, {
      sourcePath: sourceDir,
      fromRepo: "owner/repo",
      skillPath: "skills/delta",
      ref: "main",
      sourceType: "github",
      sourceUrl: "https://example.com/owner/repo",
      originKind: "derived-from-upstream",
      localModifications: true,
    });

    expect(result.skill.origin_kind).toBe("derived-from-upstream");
    expect(result.skill.source_kind).toBe("upstream");
    expect(result.skill.upstream?.repo).toBe("owner/repo");
    expect(result.skill.upstream?.sourceUrl).toBe("https://example.com/owner/repo");
  });

  test("adopts a skill into a category subdirectory", async () => {
    const repoRoot = await makeTempDir("skillctl-adopt-");
    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await writeReadme(repoRoot, "# skillctl\n");
    const sourceRoot = await makeTempDir("skillctl-source-");
    const sourceDir = await writeSkill(sourceRoot, "epsilon", "body");

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
      destinationSubdir: "frontend-and-design",
    });

    expect(result.skill.canonical_rel_path).toBe("skills/frontend-and-design/epsilon");
    expect(result.destinationDir).toBe(path.join(repoRoot, "skills", "frontend-and-design", "epsilon"));
  });

  test("strips local runtime artifacts during adoption", async () => {
    const repoRoot = await makeTempDir("skillctl-adopt-");
    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await writeReadme(repoRoot, "# skillctl\n");
    const sourceRoot = await makeTempDir("skillctl-source-");
    const sourceDir = await writeSkill(sourceRoot, "gamma", "body");
    await fs.mkdir(path.join(sourceDir, ".venv", "bin"), { recursive: true });
    await fs.mkdir(path.join(sourceDir, "__pycache__"), { recursive: true });
    await fs.writeFile(path.join(sourceDir, ".venv", "bin", "python"), "python", "utf8");
    await fs.writeFile(path.join(sourceDir, "__pycache__", "skill.pyc"), "compiled", "utf8");
    await fs.writeFile(path.join(sourceDir, "metadata.json"), "{\"private\":true}\n", "utf8");

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

    await expect(fs.access(path.join(result.destinationDir, ".venv"))).rejects.toThrow();
    await expect(fs.access(path.join(result.destinationDir, "__pycache__"))).rejects.toThrow();
    await expect(fs.access(path.join(result.destinationDir, "metadata.json"))).rejects.toThrow();
  });
});
