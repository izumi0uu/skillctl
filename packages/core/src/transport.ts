import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import os from "node:os";

import { getAdapter } from "./adapters.js";
import { copyDir, ensureDir, fileExists } from "./fs.js";
import type { AgentId, CatalogSkill, SkillctlCatalog, SkillctlConfig, SyncResult } from "./types.js";

const execFileAsync = promisify(execFile);

function managedInstallSet(catalog: SkillctlCatalog, agent: AgentId): CatalogSkill[] {
  return catalog.skills.filter((skill) => skill.managed && skill.targets.includes(agent));
}

function installableSkillSet(catalog: SkillctlCatalog, agent: AgentId): CatalogSkill[] {
  return managedInstallSet(catalog, agent).filter((skill) => skill.visibility === "public");
}

function agentArg(agent: AgentId): string {
  return getAdapter(agent).skillsCliAgent ?? agent;
}

function normalizeSourcePath(repoRoot: string, relPath?: string): string | null {
  if (!relPath) {
    return null;
  }
  return path.resolve(repoRoot, relPath);
}

async function runSkillsCliForAgent(repoRoot: string, config: SkillctlConfig, agent: AgentId, skills: CatalogSkill[]): Promise<{ command: string[]; skipped: SyncResult["skipped"]; copied: SyncResult["copied"] }> {
  const skipped: SyncResult["skipped"] = [];
  const copied: SyncResult["copied"] = [];
  const transportCommand = [config.transport.command, ...config.transport.args];

  for (const skill of skills) {
    const sourceDir = normalizeSourcePath(repoRoot, skill.canonical_rel_path);
    if (!sourceDir) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "missing canonical path" });
      continue;
    }

    const args = [
      ...config.transport.args,
      "add",
      sourceDir,
      "-g",
      "-a",
      agentArg(agent),
      "-s",
      skill.skill_id,
      "--copy",
      "-y",
    ];

    await execFileAsync(config.transport.command, args, {
      cwd: repoRoot,
      env: process.env,
      timeout: 30000,
    });

    copied.push({ agent, skillId: skill.skill_id });
  }

  return {
    command: transportCommand,
    skipped,
    copied,
  };
}

async function mirrorSharedInstallToAdapter(repoRoot: string, agent: AgentId, copiedSkills: string[]): Promise<void> {
  void repoRoot;
  const sharedRoot = path.join(os.homedir(), ".agents", "skills");
  const installDir = getAdapter(agent).installDir();
  await ensureDir(installDir);

  for (const skillId of copiedSkills) {
    const sharedSkillDir = path.join(sharedRoot, skillId);
    if (!await fileExists(sharedSkillDir)) {
      continue;
    }
    await copyDir(sharedSkillDir, path.join(installDir, skillId));
  }
}

export async function syncViaSkillsCli(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<SyncResult> {
  const copied: SyncResult["copied"] = [];
  const skipped: SyncResult["skipped"] = [];
  const managedIndexesUpdated: SyncResult["managedIndexesUpdated"] = [];
  const transportRuns: NonNullable<SyncResult["transportRuns"]> = [];

  for (const agent of config.enabledAdapters) {
    const installable = installableSkillSet(catalog, agent);
    const privateOnly = managedInstallSet(catalog, agent).filter((skill) => skill.visibility !== "public");

    for (const skill of privateOnly) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "private skill not synced to public agent dirs" });
    }

    if (installable.length > 0) {
      const result = await runSkillsCliForAgent(repoRoot, config, agent, installable);
      copied.push(...result.copied);
      skipped.push(...result.skipped);
      await mirrorSharedInstallToAdapter(repoRoot, agent, result.copied.map((entry) => entry.skillId));
      transportRuns.push({
        agent,
        command: [config.transport.command, ...config.transport.args],
      });
    }

    managedIndexesUpdated.push(agent);
  }

  return { copied, skipped, managedIndexesUpdated, transportRuns };
}

export async function transportHealth(config: SkillctlConfig): Promise<{ ok: boolean; detail: string }> {
  if (config.transport.mode !== "skills-cli") {
    return { ok: true, detail: "copy fallback selected" };
  }

  try {
    await execFileAsync(config.transport.command, [...config.transport.args, "--help"], {
      cwd: process.cwd(),
      env: process.env,
      timeout: 10000,
    });
    return { ok: true, detail: "skills CLI available" };
  } catch (error) {
    return {
      ok: false,
      detail: `skills CLI unavailable: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}
