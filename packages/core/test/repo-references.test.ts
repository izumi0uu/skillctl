import fs from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  emptyRepoReferenceRegistry,
  loadRepoReferenceRegistry,
  upsertRepoReference,
  writeRepoReferenceRegistry,
} from "../src/repo-references.js";
import { initRepo } from "../src/init.js";
import { makeTempDir } from "./helpers.js";

describe("repo references", () => {
  test("loads an empty registry when the file does not exist yet", async () => {
    const repoRoot = await makeTempDir("skillctl-repo-refs-");

    const registry = await loadRepoReferenceRegistry(repoRoot);

    expect(registry).toEqual(emptyRepoReferenceRegistry());
  });

  test("init creates the repo reference registry", async () => {
    const repoRoot = await makeTempDir("skillctl-init-refs-");

    const result = await initRepo(repoRoot);

    expect(result.created).toContain("skillctl.repo-references.json");
    const raw = JSON.parse(await fs.readFile(path.join(repoRoot, "skillctl.repo-references.json"), "utf8")) as { references: unknown[] };
    expect(raw.references).toEqual([]);
  });

  test("upsert adds and replaces repo references by id", async () => {
    const registry = emptyRepoReferenceRegistry();

    const created = upsertRepoReference(registry, {
      id: "adhd",
      display_name: "ADHD",
      category: "knowledge-and-research",
      mode: "reference-only",
      repo: "UditAkhourii/adhd",
      ref: "main",
      sourceType: "github",
      sourceUrl: "https://github.com/UditAkhourii/adhd",
      primarySkillPaths: ["skills/adhd"],
      why: "Track as a reference-only repo.",
    });

    expect(created.created).toBe(true);
    expect(registry.references).toHaveLength(1);

    expect(() => upsertRepoReference(registry, {
      id: "adhd",
      mode: "reference-only",
      sourceType: "github",
      sourceUrl: "https://github.com/UditAkhourii/adhd",
      primarySkillPaths: ["skills/adhd"],
      why: "Duplicate should fail without replace.",
    })).toThrow(/already exists/);

    const replaced = upsertRepoReference(registry, {
      id: "adhd",
      display_name: "ADHD Updated",
      category: "knowledge-and-research",
      mode: "reference-only",
      repo: "UditAkhourii/adhd",
      ref: "main",
      sourceType: "github",
      sourceUrl: "https://github.com/UditAkhourii/adhd",
      primarySkillPaths: ["skills/adhd"],
      referencePaths: ["README.md"],
      why: "Track as a reference-only repo.",
    }, { replace: true });

    expect(replaced.created).toBe(false);
    expect(registry.references[0]?.display_name).toBe("ADHD Updated");
    expect(registry.references[0]?.referencePaths).toEqual(["README.md"]);
  });

  test("writes and reloads the repo reference registry", async () => {
    const repoRoot = await makeTempDir("skillctl-repo-refs-persist-");
    const registry = emptyRepoReferenceRegistry();
    upsertRepoReference(registry, {
      id: "adhd",
      mode: "reference-only",
      sourceType: "github",
      sourceUrl: "https://github.com/UditAkhourii/adhd",
      primarySkillPaths: ["skills/adhd"],
      why: "Track as a reference-only repo.",
    });

    await writeRepoReferenceRegistry(repoRoot, registry);

    await expect(loadRepoReferenceRegistry(repoRoot)).resolves.toEqual(registry);
  });
});
