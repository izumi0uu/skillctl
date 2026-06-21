import fs from "node:fs/promises";
import path from "node:path";

import { afterEach, describe, expect, test, vi } from "vitest";

import { runCli } from "../src/index.js";

async function makeRepoRoot(prefix: string): Promise<string> {
  const repoRoot = await fs.mkdtemp(path.join(process.cwd(), prefix));
  await fs.writeFile(path.join(repoRoot, "pnpm-workspace.yaml"), "packages:\n  - packages/*\n", "utf8");
  await fs.writeFile(path.join(repoRoot, "package.json"), "{ \"name\": \"skillctl-test-root\" }\n", "utf8");
  return repoRoot;
}

const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

afterEach(() => {
  logSpy.mockClear();
});

describe("runCli refs", () => {
  test("lists repo references after init", async () => {
    const repoRoot = await makeRepoRoot(".tmp-refs-list-");

    await expect(runCli(["init"], repoRoot)).resolves.toBe(0);
    await expect(runCli(["refs"], repoRoot)).resolves.toBe(0);

    const output = logSpy.mock.calls.at(-1)?.[0];
    expect(typeof output).toBe("string");
    const parsed = JSON.parse(output as string) as { references: unknown[] };
    expect(parsed.references).toEqual([]);

    await fs.rm(repoRoot, { recursive: true, force: true });
  });

  test("adds a repo reference without touching the managed catalog", async () => {
    const repoRoot = await makeRepoRoot(".tmp-refs-add-");

    await expect(runCli(["init"], repoRoot)).resolves.toBe(0);
    await expect(runCli([
      "refs",
      "add",
      "--id", "adhd",
      "--display-name", "ADHD",
      "--category", "knowledge-and-research",
      "--repo", "UditAkhourii/adhd",
      "--ref", "main",
      "--source-type", "github",
      "--source-url", "https://github.com/UditAkhourii/adhd",
      "--primary-skill-path", "skills/adhd",
      "--reference-path", "README.md",
      "--reference-path", "SOURCE-SPEC.md",
      "--tag", "brainstorming",
      "--tag", "parallel-thinking",
      "--why", "Track this repo as a reference-only methodology source.",
      "--notes", "Do not install through the managed skills pipeline.",
    ], repoRoot)).resolves.toBe(0);

    const refsRaw = JSON.parse(await fs.readFile(path.join(repoRoot, "skillctl.repo-references.json"), "utf8")) as {
      references: Array<{ id: string; sourceUrl: string; primarySkillPaths: string[]; mode: string }>;
    };
    expect(refsRaw.references).toHaveLength(1);
    expect(refsRaw.references[0]).toEqual(expect.objectContaining({
      id: "adhd",
      sourceUrl: "https://github.com/UditAkhourii/adhd",
      primarySkillPaths: ["skills/adhd"],
      mode: "reference-only",
    }));

    const catalogRaw = JSON.parse(await fs.readFile(path.join(repoRoot, "skillctl.catalog.json"), "utf8")) as { skills: unknown[] };
    expect(catalogRaw.skills).toEqual([]);

    await fs.rm(repoRoot, { recursive: true, force: true });
  });
});
