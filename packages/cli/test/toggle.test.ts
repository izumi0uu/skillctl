import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { defaultConfig, loadCatalog, writeCatalog } from "@skillctl/core";
import { runCli } from "../src/index.js";

let repoRoot: string;
let installDir: string;
const log = vi.spyOn(console, "log").mockImplementation(() => {});

beforeEach(async () => {
  repoRoot = await fs.mkdtemp(path.join(os.tmpdir(), "skillctl-toggle-"));
  installDir = path.join(repoRoot, "home", ".codex", "skills");
  vi.spyOn(os, "homedir").mockReturnValue(path.join(repoRoot, "home"));
  await fs.writeFile(path.join(repoRoot, "pnpm-workspace.yaml"), "packages: []\n");
  await fs.writeFile(path.join(repoRoot, "package.json"), '{"name":"skillctl-test-root"}');
  await fs.writeFile(path.join(repoRoot, "README.md"), "# Test\n");
  await fs.writeFile(path.join(repoRoot, "skillctl.config.json"), JSON.stringify({
    ...defaultConfig(), enabledAdapters: ["codex"],
    transport: { mode: "copy-fallback", command: "unused", args: [] },
  }));
  await fs.mkdir(path.join(repoRoot, "skills", "alpha"), { recursive: true });
  await fs.writeFile(path.join(repoRoot, "skills", "alpha", "SKILL.md"), "---\nname: alpha\ndescription: Test skill\n---\n\nExplain things.\n");
  await writeCatalog(repoRoot, { version: 1, generatedBy: "test", skills: [{
    skill_id: "alpha", visibility: "public", source_kind: "local-public",
    origin_kind: "local-authored", hash: "placeholder", managed: true,
    targets: ["codex"], canonical_rel_path: "skills/alpha",
  }] });
});

afterEach(async () => {
  vi.mocked(os.homedir).mockRestore();
  log.mockClear();
  await fs.rm(repoRoot, { recursive: true, force: true });
});

describe("enable and disable", () => {
  test("syncs by default, removes the install, and restores it on enable", async () => {
    await runCli(["enable", "alpha"], repoRoot);
    await expect(fs.access(path.join(installDir, "alpha", "SKILL.md"))).resolves.toBeUndefined();
    await runCli(["disable", "alpha", "--json"], repoRoot);
    expect(JSON.parse(log.mock.calls.at(-1)![0])).toMatchObject({ enabled: false, changed: true, synced: true });
    await expect(fs.access(path.join(installDir, "alpha"))).rejects.toThrow();
    await expect(fs.access(path.join(repoRoot, "skills", "alpha", "SKILL.md"))).resolves.toBeUndefined();
    await runCli(["disable", "alpha", "--json"], repoRoot);
    expect(JSON.parse(log.mock.calls.at(-1)![0])).toMatchObject({ changed: false, synced: true });
    await runCli(["enable", "alpha"], repoRoot);
    expect((await loadCatalog(repoRoot)).skills[0].enabled).toBeUndefined();
    await expect(fs.access(path.join(installDir, "alpha", "SKILL.md"))).resolves.toBeUndefined();
    expect(await runCli(["doctor", "--json"], repoRoot)).toBe(0);
  });

  test("no-sync preserves installs and discover preserves the disabled setting", async () => {
    await runCli(["enable", "alpha"], repoRoot);
    await runCli(["disable", "alpha", "--no-sync", "--json"], repoRoot);
    expect(JSON.parse(log.mock.calls.at(-1)![0])).toMatchObject({ synced: false });
    await expect(fs.access(path.join(installDir, "alpha"))).resolves.toBeUndefined();
    await runCli(["discover"], repoRoot);
    expect((await loadCatalog(repoRoot)).skills[0].enabled).toBe(false);
  });

  test.each([[], ["missing"], ["alpha", "extra"], ["alpha", "--agent", "codex"], ["--json"]])("rejects invalid arguments %j without changing the catalog", async (...args) => {
    const before = await fs.readFile(path.join(repoRoot, "skillctl.catalog.json"), "utf8");
    await expect(runCli(["disable", ...args], repoRoot)).rejects.toThrow();
    expect(await fs.readFile(path.join(repoRoot, "skillctl.catalog.json"), "utf8")).toBe(before);
  });

  test("rejects unmanaged skills", async () => {
    const catalog = await loadCatalog(repoRoot);
    catalog.skills[0].managed = false;
    await writeCatalog(repoRoot, catalog);
    await expect(runCli(["disable", "alpha"], repoRoot)).rejects.toThrow("not managed");
  });

  test("sync failure reports the saved setting and retry command", async () => {
    await fs.writeFile(path.join(repoRoot, "home"), "not a directory");
    await expect(runCli(["disable", "alpha"], repoRoot)).rejects.toThrow("Saved alpha as disabled, but sync failed. Run skillctl sync to retry.");
    expect((await loadCatalog(repoRoot)).skills[0].enabled).toBe(false);
  });
});
