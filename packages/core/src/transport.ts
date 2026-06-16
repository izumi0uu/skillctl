import { execFile } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { ensureReadmeSourceRegistry, expectedSkillRenderedHash } from "./attribution.js";
import { getAdapter } from "./adapters.js";
import { managedSkillsForAgent } from "./catalog.js";
import { DistributionPolicyCache, installableSkillsForAgent } from "./distribution.js";
import { copyDir, ensureDir, fileExists, removeDirIfExists } from "./fs.js";
import { writeManagedIndex } from "./indexes.js";
import type {
  AgentId,
  BootstrapUpstreamResult,
  CatalogSkill,
  ResolvedTransportInvocation,
  SkillctlCatalog,
  SkillctlConfig,
  SyncResult,
  TransportHealthReport,
} from "./types.js";

const execFileAsync = promisify(execFile);

export type SyncStage = "transport" | "start" | "agent" | "skill" | "mirror" | "attribution" | "done";
export interface SyncProgressEvent {
  stage: SyncStage;
  agent?: AgentId;
  skillId?: string;
  copied?: number;
  total?: number;
  message?: string;
}
export type SyncProgressCallback = (event: SyncProgressEvent) => void;

export type BootstrapStage = "deps" | "build" | "resolve" | "done";
export interface BootstrapProgressEvent {
  stage: BootstrapStage;
  message?: string;
}
export type BootstrapProgressCallback = (event: BootstrapProgressEvent) => void;

function agentArg(agent: AgentId): string {
  return getAdapter(agent).skillsCliAgent ?? agent;
}

function normalizeSourcePath(repoRoot: string, relPath?: string): string | null {
  if (!relPath) {
    return null;
  }
  return path.resolve(repoRoot, relPath);
}

function embeddedRepoPath(config: SkillctlConfig): string | null {
  return config.transport.embeddedRepoPath ?? null;
}

function runtimeInvocation(scriptPath: string): Pick<ResolvedTransportInvocation, "command" | "args" | "env"> {
  if (process.versions.electron) {
    return {
      command: process.execPath,
      args: [scriptPath],
      env: {
        ELECTRON_RUN_AS_NODE: "1",
      },
    };
  }

  return {
    command: process.execPath,
    args: [scriptPath],
  };
}

function invocationEnv(invocation: ResolvedTransportInvocation): NodeJS.ProcessEnv {
  return invocation.env ? { ...process.env, ...invocation.env } : process.env;
}

interface SkillsCliBatch {
  sourceDir: string;
  skills: CatalogSkill[];
}

function batchTimeoutMs(skillCount: number): number {
  return Math.max(30_000, Math.min(300_000, skillCount * 10_000));
}

async function resolveTransportInvocation(config: SkillctlConfig): Promise<ResolvedTransportInvocation> {
  const embeddedRepo = embeddedRepoPath(config);
  if (embeddedRepo) {
    const packageJson = path.join(embeddedRepo, "package.json");
    const sourceCli = path.join(embeddedRepo, "src", "cli.ts");
    const builtCli = path.join(embeddedRepo, "bin", "cli.mjs");
    const distCli = path.join(embeddedRepo, "dist", "cli.mjs");
    const nodeModules = path.join(embeddedRepo, "node_modules");
    const dist = path.join(embeddedRepo, "dist");

    if (await fileExists(packageJson)) {
      const hasNodeModules = await fileExists(nodeModules);
      const hasSourceCli = await fileExists(sourceCli);
      const hasDist = await fileExists(dist);
      const hasBuiltCli = await fileExists(builtCli);
      const hasDistCli = await fileExists(distCli);

      if (hasDist && hasDistCli) {
        return {
          ...runtimeInvocation(hasBuiltCli ? builtCli : distCli),
          cwd: embeddedRepo,
          source: "embedded-dist",
          detail: `embedded skills build ready at ${embeddedRepo}`,
        };
      }

      if (hasNodeModules && hasSourceCli) {
        return {
          ...runtimeInvocation(sourceCli),
          cwd: embeddedRepo,
          source: "embedded-source",
          detail: `embedded skills repo ready at ${embeddedRepo}`,
        };
      }

      return {
        command: config.transport.command,
        args: config.transport.args,
        cwd: process.cwd(),
        source: "fallback",
        detail: `embedded skills repo found at ${embeddedRepo} but is not bootstrapped; run skillctl bootstrap-upstream`,
      };
    }
  }

  return {
    command: config.transport.command,
    args: config.transport.args,
    cwd: process.cwd(),
    source: "fallback",
    detail: "embedded skills repo not configured or missing; using fallback CLI transport",
  };
}

async function runSkillsCliForAgent(
  repoRoot: string,
  invocation: ResolvedTransportInvocation,
  agent: AgentId,
  skills: CatalogSkill[],
  onCopied?: (skillId: string) => void,
): Promise<{ commands: string[][]; skipped: SyncResult["skipped"]; copied: SyncResult["copied"] }> {
  const skipped: SyncResult["skipped"] = [];
  const copied: SyncResult["copied"] = [];
  const commands: string[][] = [];

  const resolved = skills.flatMap((skill) => {
    const sourceDir = normalizeSourcePath(repoRoot, skill.canonical_rel_path);
    if (!sourceDir) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "missing canonical path" });
      return [];
    }
    return [{ skill, sourceDir }];
  });

  const sharedSkillsRoot = path.join(repoRoot, "skills");
  const allUnderSharedRoot = resolved.length > 0
    && resolved.every(({ sourceDir }) => sourceDir === sharedSkillsRoot || sourceDir.startsWith(`${sharedSkillsRoot}${path.sep}`));

  const batches: SkillsCliBatch[] = [];
  if (allUnderSharedRoot) {
    batches.push({ sourceDir: sharedSkillsRoot, skills: resolved.map(({ skill }) => skill) });
  } else {
    const byParent = new Map<string, CatalogSkill[]>();
    for (const entry of resolved) {
      const parentDir = path.dirname(entry.sourceDir);
      const group = byParent.get(parentDir) ?? [];
      group.push(entry.skill);
      byParent.set(parentDir, group);
    }
    for (const [sourceDir, groupedSkills] of byParent) {
      batches.push({ sourceDir, skills: groupedSkills });
    }
  }

  for (const batch of batches) {
    const args = [
      ...invocation.args,
      "add",
      batch.sourceDir,
      "-g",
      "-a",
      agentArg(agent),
      "--copy",
      "-y",
      ...batch.skills.flatMap((skill) => ["-s", skill.skill_id]),
    ];

    await execFileAsync(invocation.command, args, {
      cwd: invocation.cwd,
      env: invocationEnv(invocation),
      timeout: batchTimeoutMs(batch.skills.length),
    });

    commands.push([invocation.command, ...args]);
    for (const skill of batch.skills) {
      copied.push({ agent, skillId: skill.skill_id });
      onCopied?.(skill.skill_id);
    }
  }

  return {
    commands,
    skipped,
    copied,
  };
}

async function mirrorSharedInstallToAdapter(agent: AgentId, copiedSkills: string[]): Promise<void> {
  const sharedRoot = path.join(os.homedir(), ".agents", "skills");
  const installDir = getAdapter(agent).installDir();
  await ensureDir(installDir);

  await Promise.all(copiedSkills.map(async (skillId) => {
    const sharedSkillDir = path.join(sharedRoot, skillId);
    if (!await fileExists(sharedSkillDir)) {
      return;
    }
    await copyDir(sharedSkillDir, path.join(installDir, skillId));
  }));
}

// Apply the source-attribution footer to each skill's final per-agent install
// location. This must run AFTER mirrorSharedInstallToAdapter: for universal
// agents the upstream CLI copies into ~/.agents/skills and the mirror brings it
// into the adapter dir, so footering the adapter dir before the mirror would be
// silently lost (and leave installs in permanent footer drift).
async function renderInstalledAttribution(agent: AgentId, skills: CatalogSkill[], copied: SyncResult["copied"]): Promise<void> {
  const copiedIds = new Set(copied.map((entry) => entry.skillId));
  const installRoot = getAdapter(agent).installDir();

  await Promise.all(skills.map(async (skill) => {
    if (!copiedIds.has(skill.skill_id)) {
      return;
    }
    const installedDir = path.join(installRoot, skill.skill_id);
    if (await fileExists(installedDir)) {
      await expectedSkillRenderedHash(installedDir, skill);
    }
  }));
}

export async function syncViaSkillsCli(
  repoRoot: string,
  config: SkillctlConfig,
  catalog: SkillctlCatalog,
  onProgress?: SyncProgressCallback,
): Promise<SyncResult> {
  const copied: SyncResult["copied"] = [];
  const skipped: SyncResult["skipped"] = [];
  const managedIndexesUpdated: SyncResult["managedIndexesUpdated"] = [];
  const transportRuns: NonNullable<SyncResult["transportRuns"]> = [];
  const invocation = await resolveTransportInvocation(config);
  const cache = new DistributionPolicyCache();

  onProgress?.({ stage: "transport", message: invocation.detail });

  type AgentPlan = {
    agent: AgentId;
    adapter: ReturnType<typeof getAdapter>;
    installableSet: Awaited<ReturnType<typeof installableSkillsForAgent>>;
    installable: CatalogSkill[];
  };

  const plan: AgentPlan[] = [];
  for (const agent of config.enabledAdapters) {
    const adapter = getAdapter(agent);
    await ensureDir(adapter.installDir());
    const installableSet = await installableSkillsForAgent(repoRoot, catalog, agent, cache);
    const installable = installableSet.installable.filter((skill) => skill.visibility === "public");
    plan.push({ agent, adapter, installableSet, installable });
  }

  const total = plan.reduce((sum, entry) => sum + entry.installable.length, 0);
  onProgress?.({ stage: "start", total, copied: 0 });

  let copiedCount = 0;
  for (const { agent, adapter, installableSet, installable } of plan) {
    onProgress?.({ stage: "agent", agent, copied: copiedCount, total });
    const privateOnly = managedSkillsForAgent(catalog, agent).filter((skill) => skill.visibility !== "public");

    for (const skill of installableSet.missingCanonicalPath) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "missing canonical path" });
    }

    for (const missing of installableSet.missingSourceDir) {
      skipped.push({ agent, skillId: missing.skill.skill_id, reason: `source missing: ${missing.sourceDir}` });
    }

    for (const blocked of installableSet.blocked) {
      await removeDirIfExists(path.join(adapter.installDir(), blocked.skill.skill_id));
      skipped.push({ agent, skillId: blocked.skill.skill_id, reason: blocked.reason });
    }

    for (const skill of privateOnly) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "private skill not synced to public agent dirs" });
    }

    if (installable.length > 0) {
      const result = await runSkillsCliForAgent(repoRoot, invocation, agent, installable, (skillId) => {
        copiedCount += 1;
        onProgress?.({ stage: "skill", agent, skillId, copied: copiedCount, total });
      });
      copied.push(...result.copied);
      skipped.push(...result.skipped);
      onProgress?.({ stage: "mirror", agent, copied: copiedCount, total });
      await mirrorSharedInstallToAdapter(agent, result.copied.map((entry) => entry.skillId));
      await renderInstalledAttribution(agent, installable, result.copied);
      for (const command of result.commands) {
        transportRuns.push({ agent, command });
      }
    }

    await writeManagedIndex(config.stateDir!, agent, installable);
    managedIndexesUpdated.push(agent);
  }

  onProgress?.({ stage: "attribution", copied: copiedCount, total });
  await ensureReadmeSourceRegistry(repoRoot, catalog);
  onProgress?.({ stage: "done", copied: copiedCount, total });

  return { copied, skipped, managedIndexesUpdated, transportRuns };
}

export async function transportHealth(config: SkillctlConfig): Promise<TransportHealthReport> {
  if (config.transport.mode !== "skills-cli") {
    const invocation: ResolvedTransportInvocation = {
      command: config.transport.command,
      args: config.transport.args,
      cwd: process.cwd(),
      source: "fallback",
      detail: "copy fallback selected",
    };
    return {
      status: "ok",
      detail: "copy fallback selected",
      invocation,
    };
  }

  const invocation = await resolveTransportInvocation(config);

  if (invocation.source === "fallback" && invocation.detail.includes("not bootstrapped")) {
    return {
      status: "warn",
      detail: invocation.detail,
      invocation,
    };
  }

  try {
    await execFileAsync(invocation.command, [...invocation.args, "--help"], {
      cwd: invocation.cwd,
      env: invocationEnv(invocation),
      timeout: 10000,
    });
    return {
      status: "ok",
      detail: invocation.detail,
      invocation,
    };
  } catch (error) {
    return {
      status: "error",
      detail: `skills CLI unavailable: ${error instanceof Error ? error.message : String(error)}`,
      invocation,
    };
  }
}

export async function bootstrapEmbeddedSkills(
  config: SkillctlConfig,
  onProgress?: BootstrapProgressCallback,
): Promise<BootstrapUpstreamResult> {
  const embeddedRepo = embeddedRepoPath(config);
  if (!embeddedRepo) {
    throw new Error("transport.embeddedRepoPath is not configured");
  }

  const packageJson = path.join(embeddedRepo, "package.json");
  if (!await fileExists(packageJson)) {
    throw new Error(`embedded skills repo missing: ${embeddedRepo}`);
  }

  const steps: string[] = [];

  if (!await fileExists(path.join(embeddedRepo, "node_modules"))) {
    onProgress?.({ stage: "deps", message: "installing upstream dependencies" });
    await execFileAsync("pnpm", ["install", "--ignore-workspace", "--reporter", "append-only"], {
      cwd: embeddedRepo,
      env: process.env,
      timeout: 180000,
    });
    steps.push("installed upstream dependencies");
  } else {
    steps.push("upstream dependencies already installed");
  }

  if (!await fileExists(path.join(embeddedRepo, "dist"))) {
    onProgress?.({ stage: "build", message: "building upstream CLI" });
    await execFileAsync("pnpm", ["run", "build"], {
      cwd: embeddedRepo,
      env: process.env,
      timeout: 180000,
    });
    steps.push("built upstream CLI");
  } else {
    steps.push("upstream CLI build already present");
  }

  onProgress?.({ stage: "resolve", message: "resolving transport" });
  const invocation = await resolveTransportInvocation(config);
  onProgress?.({ stage: "done" });
  return {
    embeddedRepoPath: embeddedRepo,
    steps,
    invocation: {
      command: [invocation.command, ...invocation.args],
      source: invocation.source,
    },
  };
}
