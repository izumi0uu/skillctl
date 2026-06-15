import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { runHealthSuite } from "../src/health-suite.js";

const originalHome = process.env.HOME;

async function makeTempDir(prefix: string): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), prefix));
}

async function writeSkill(dirPath: string, skillId: string): Promise<string> {
  const skillDir = path.join(dirPath, skillId);
  await fs.mkdir(skillDir, { recursive: true });
  await fs.writeFile(path.join(skillDir, "SKILL.md"), `---\nname: ${skillId}\ndescription: test skill ${skillId}\n---\n\n# ${skillId}\n`, "utf8");
  return skillDir;
}

async function writeJson(filePath: string, data: unknown): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

afterEach(async () => {
  if (originalHome) {
    process.env.HOME = originalHome;
  } else {
    delete process.env.HOME;
  }
});

describe("runHealthSuite", () => {
  test("returns a healthy summary for a portable local skill", async () => {
    const repoRoot = await makeTempDir(".tmp-health-suite-ok-");
    const fakeHome = await makeTempDir(".tmp-health-home-");
    process.env.HOME = fakeHome;

    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await writeSkill(path.join(repoRoot, "skills"), "alpha");
    await fs.writeFile(path.join(repoRoot, "README.md"), "# skillctl\n", "utf8");
    await writeJson(path.join(repoRoot, "skillctl.config.json"), {
      sourceRoots: [{ path: "./skills", visibility: "public", managedByDefault: true }],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
    });
    await writeJson(path.join(repoRoot, "skillctl.catalog.json"), {
      version: 1,
      generatedBy: "test",
      skills: [],
    });

    const report = await runHealthSuite(repoRoot);

    expect(report.ok).toBe(true);
    expect(report.exitCode).toBe(0);
    expect(report.steps).toEqual([
      expect.objectContaining({ name: "discover", exitCode: 0 }),
      expect.objectContaining({ name: "sync", exitCode: 0 }),
      expect.objectContaining({ name: "doctor", exitCode: 0 }),
      expect.objectContaining({ name: "verify-sources", exitCode: 0 }),
    ]);
    expect(report.summary.catalog.managedSkills).toBe(1);
    await expect(fs.access(path.join(fakeHome, ".codex", "skills", "alpha", "SKILL.md"))).resolves.toBeUndefined();
  });

  test("surfaces discovery conflicts as exit code 2", async () => {
    const repoRoot = await makeTempDir(".tmp-health-suite-conflict-");
    const fakeHome = await makeTempDir(".tmp-health-home-");
    process.env.HOME = fakeHome;

    await fs.mkdir(path.join(repoRoot, "skills"), { recursive: true });
    await fs.mkdir(path.join(repoRoot, "private-skills"), { recursive: true });
    await writeSkill(path.join(repoRoot, "skills"), "alpha");
    await writeSkill(path.join(repoRoot, "private-skills"), "alpha");
    await fs.writeFile(path.join(repoRoot, "README.md"), "# skillctl\n", "utf8");
    await writeJson(path.join(repoRoot, "skillctl.config.json"), {
      sourceRoots: [
        { path: "./skills", visibility: "public", managedByDefault: true },
        { path: "./private-skills", visibility: "private", managedByDefault: true },
      ],
      privateRoots: ["./private-skills"],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
    });
    await writeJson(path.join(repoRoot, "skillctl.catalog.json"), {
      version: 1,
      generatedBy: "test",
      skills: [],
    });

    const report = await runHealthSuite(repoRoot);

    expect(report.ok).toBe(false);
    expect(report.exitCode).toBe(2);
    expect(report.summary.discover.conflicts).toEqual([
      expect.objectContaining({ skillId: "alpha" }),
    ]);
    expect(report.steps[0]).toEqual(expect.objectContaining({ name: "discover", exitCode: 2 }));
    expect(report.steps[1]).toEqual(expect.objectContaining({ name: "sync", detail: expect.stringContaining("skipped") }));
    const persistedCatalog = JSON.parse(await fs.readFile(path.join(repoRoot, "skillctl.catalog.json"), "utf8")) as { skills: unknown[] };
    expect(persistedCatalog.skills).toHaveLength(0);
  });
});
