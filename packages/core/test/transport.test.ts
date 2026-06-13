import fs from "node:fs/promises";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { bootstrapEmbeddedSkills, transportHealth } from "../src/transport.js";
import { makeTempDir } from "./helpers.js";

const originalHome = process.env.HOME;

afterEach(() => {
  if (originalHome) {
    process.env.HOME = originalHome;
  }
});

describe("transportHealth", () => {
  test("accepts copy fallback without probing", async () => {
    const status = await transportHealth({
      sourceRoots: [],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
        embeddedRepoPath: "/tmp/vercel-skills",
      },
      stateDir: "/tmp/skillctl-state",
    });
    expect(status.status).toBe("ok");
  });

  test("warns when embedded repo exists but is not bootstrapped", async () => {
    const repoRoot = await makeTempDir("skillctl-transport-");
    const embeddedRepo = path.join(repoRoot, "vercel-skills");
    await fs.mkdir(path.join(embeddedRepo, "src"), { recursive: true });
    await fs.writeFile(path.join(embeddedRepo, "package.json"), JSON.stringify({ name: "skills" }), "utf8");
    await fs.writeFile(path.join(embeddedRepo, "src", "cli.ts"), "console.log('skills');\n", "utf8");

    const status = await transportHealth({
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
    });

    expect(status.status).toBe("warn");
    expect(status.invocation.source).toBe("fallback");
    expect(status.detail).toContain("not bootstrapped");
  });
});

describe("bootstrapEmbeddedSkills", () => {
  test("uses embedded source transport once node_modules are present", async () => {
    const repoRoot = await makeTempDir("skillctl-bootstrap-");
    const embeddedRepo = path.join(repoRoot, "vercel-skills");
    await fs.mkdir(path.join(embeddedRepo, "src"), { recursive: true });
    await fs.mkdir(path.join(embeddedRepo, "node_modules"), { recursive: true });
    await fs.mkdir(path.join(embeddedRepo, "dist"), { recursive: true });
    await fs.writeFile(path.join(embeddedRepo, "package.json"), JSON.stringify({ name: "skills" }), "utf8");
    await fs.writeFile(path.join(embeddedRepo, "src", "cli.ts"), "console.log('skills');\n", "utf8");

    const result = await bootstrapEmbeddedSkills({
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
    });

    expect(result.steps).toContain("upstream dependencies already installed");
    expect(result.steps).toContain("upstream CLI build already present");
    expect(result.invocation.source).toBe("embedded-source");
    expect(result.invocation.command).toEqual(["node", path.join(embeddedRepo, "src", "cli.ts")]);
  });
});
