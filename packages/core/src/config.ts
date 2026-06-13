import path from "node:path";

import { readJson, writeJson } from "./fs.js";
import { CONFIG_FILE, DEFAULT_EMBEDDED_SKILLS_REPO, defaultStateDir, expandHome } from "./paths.js";
import { skillctlConfigSchema } from "./schema.js";
import type { SkillctlConfig } from "./types.js";

function resolveConfigPath(repoRoot: string, inputPath: string): string {
  const expanded = expandHome(inputPath);
  return path.isAbsolute(expanded) ? expanded : path.resolve(repoRoot, expanded);
}

export function defaultConfig(): SkillctlConfig {
  return {
    sourceRoots: [
      { path: "./skills", visibility: "public", managedByDefault: true },
    ],
    privateRoots: [],
    enabledAdapters: ["claude-code", "codex", "pi", "hermes", "opencode"],
    excludeSkills: [],
    liveProbePolicy: "off",
    transport: {
      mode: "skills-cli",
      command: "npx",
      args: ["--yes", "skills"],
      embeddedRepoPath: DEFAULT_EMBEDDED_SKILLS_REPO,
    },
  };
}

export async function loadConfig(repoRoot: string): Promise<SkillctlConfig> {
  const filePath = path.join(repoRoot, CONFIG_FILE);
  const raw = await readJson<unknown>(filePath);
  const parsed = skillctlConfigSchema.parse(raw);
  return {
    ...parsed,
    sourceRoots: parsed.sourceRoots.map((root) => ({ ...root, path: resolveConfigPath(repoRoot, root.path) })),
    privateRoots: parsed.privateRoots.map((root) => resolveConfigPath(repoRoot, root)),
    transport: {
      ...parsed.transport,
      embeddedRepoPath: parsed.transport.embeddedRepoPath
        ? resolveConfigPath(repoRoot, parsed.transport.embeddedRepoPath)
        : resolveConfigPath(repoRoot, DEFAULT_EMBEDDED_SKILLS_REPO),
    },
    stateDir: parsed.stateDir ? resolveConfigPath(repoRoot, parsed.stateDir) : defaultStateDir(repoRoot),
  };
}

export async function writeDefaultConfig(repoRoot: string): Promise<void> {
  const config = defaultConfig();
  await writeJson(path.join(repoRoot, CONFIG_FILE), config);
}
