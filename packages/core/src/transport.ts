import { execFile } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { ensureReadmeSourceRegistry, expectedSkillRenderedHash } from "./attribution.js";
import { getAdapter } from "./adapters.js";
import { copyDir, ensureDir, fileExists } from "./fs.js";
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

function embeddedRepoPath(config: SkillctlConfig): string | null {
  return config.transport.embeddedRepoPath ?? null;
}

async function resolveTransportInvocation(config: SkillctlConfig): Promise<ResolvedTransportInvocation> {
  const embeddedRepo = embeddedRepoPath(config);
  if (embeddedRepo) {
    const packageJson = path.join(embeddedRepo, "package.json");
    const sourceCli = path.join(embeddedRepo, "src", "cli.ts");
    const builtCli = path.join(embeddedRepo, "bin", "cli.mjs");
    const nodeModules = path.join(embeddedRepo, "node_modules");
    const dist = path.join(embeddedRepo, "dist");

    if (await fileExists(packageJson)) {
      const hasNodeModules = await fileExists(nodeModules);
      const hasSourceCli = await fileExists(sourceCli);
      const hasDist = await fileExists(dist);
      const hasBuiltCli = await fileExists(builtCli);

      if (hasNodeModules && hasSourceCli) {
        return {
          command: "node",
          args: [sourceCli],
          cwd: embeddedRepo,
          source: "embedded-source",
          detail: `embedded skills repo ready at ${embeddedRepo}`,
        };
      }

      if (hasBuiltCli && hasDist) {
        return {
          command: "node",
          args: [builtCli],
          cwd: embeddedRepo,
          source: "embedded-dist",
          detail: `embedded skills build ready at ${embeddedRepo}`,
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
): Promise<{ command: string[]; skipped: SyncResult["skipped"]; copied: SyncResult["copied"] }> {
  const skipped: SyncResult["skipped"] = [];
  const copied: SyncResult["copied"] = [];
  const transportCommand = [invocation.command, ...invocation.args];

  for (const skill of skills) {
    const sourceDir = normalizeSourcePath(repoRoot, skill.canonical_rel_path);
    if (!sourceDir) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "missing canonical path" });
      continue;
    }

    const args = [
      ...invocation.args,
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

    await execFileAsync(invocation.command, args, {
      cwd: invocation.cwd,
      env: process.env,
      timeout: 30000,
    });

    const installedDir = path.join(getAdapter(agent).installDir(), skill.skill_id);
    if (await fileExists(installedDir)) {
      await expectedSkillRenderedHash(installedDir, skill);
    }

    copied.push({ agent, skillId: skill.skill_id });
  }

  return {
    command: transportCommand,
    skipped,
    copied,
  };
}

async function mirrorSharedInstallToAdapter(agent: AgentId, copiedSkills: string[]): Promise<void> {
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
  const invocation = await resolveTransportInvocation(config);

  for (const agent of config.enabledAdapters) {
    await ensureDir(getAdapter(agent).installDir());
    const installable = installableSkillSet(catalog, agent);
    const privateOnly = managedInstallSet(catalog, agent).filter((skill) => skill.visibility !== "public");

    for (const skill of privateOnly) {
      skipped.push({ agent, skillId: skill.skill_id, reason: "private skill not synced to public agent dirs" });
    }

    if (installable.length > 0) {
      const result = await runSkillsCliForAgent(repoRoot, invocation, agent, installable);
      copied.push(...result.copied);
      skipped.push(...result.skipped);
      await mirrorSharedInstallToAdapter(agent, result.copied.map((entry) => entry.skillId));
      transportRuns.push({
        agent,
        command: [invocation.command, ...invocation.args],
      });
    }

    managedIndexesUpdated.push(agent);
  }

  await ensureReadmeSourceRegistry(repoRoot, catalog);

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
      env: process.env,
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

export async function bootstrapEmbeddedSkills(config: SkillctlConfig): Promise<BootstrapUpstreamResult> {
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
    await execFileAsync("pnpm", ["run", "build"], {
      cwd: embeddedRepo,
      env: process.env,
      timeout: 180000,
    });
    steps.push("built upstream CLI");
  } else {
    steps.push("upstream CLI build already present");
  }

  const invocation = await resolveTransportInvocation(config);
  return {
    embeddedRepoPath: embeddedRepo,
    steps,
    invocation: {
      command: [invocation.command, ...invocation.args],
      source: invocation.source,
    },
  };
}
