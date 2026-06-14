import path from "node:path";

import type { AgentId, CatalogSkill, SkillctlCatalog } from "./types.js";
import { managedSkillsForAgent } from "./catalog.js";
import { fileExists } from "./fs.js";
import { evaluateSkillDistributionPolicy } from "./portability.js";

export interface InstallableSkillSet {
  installable: CatalogSkill[];
  blocked: Array<{ skill: CatalogSkill; reason: string }>;
  missingCanonicalPath: CatalogSkill[];
  missingSourceDir: Array<{ skill: CatalogSkill; sourceDir: string }>;
}

interface CachedPolicyEntry {
  sourceDir: string;
  policy: Awaited<ReturnType<typeof evaluateSkillDistributionPolicy>>;
}

function cacheKey(sourceDir: string, skillId: string): string {
  return `${sourceDir}::${skillId}`;
}

export class DistributionPolicyCache {
  private readonly byKey = new Map<string, CachedPolicyEntry>();

  async get(sourceDir: string, skill: CatalogSkill): Promise<CachedPolicyEntry> {
    const key = cacheKey(sourceDir, skill.skill_id);
    const existing = this.byKey.get(key);
    if (existing) {
      return existing;
    }
    const policy = await evaluateSkillDistributionPolicy(sourceDir, skill);
    const entry = { sourceDir, policy };
    this.byKey.set(key, entry);
    return entry;
  }
}

export async function installableSkillsForAgent(
  repoRoot: string,
  catalog: SkillctlCatalog,
  agent: AgentId,
  cache = new DistributionPolicyCache(),
): Promise<InstallableSkillSet> {
  const installable: CatalogSkill[] = [];
  const blocked: InstallableSkillSet["blocked"] = [];
  const missingCanonicalPath: CatalogSkill[] = [];
  const missingSourceDir: InstallableSkillSet["missingSourceDir"] = [];

  for (const skill of managedSkillsForAgent(catalog, agent)) {
    if (!skill.canonical_rel_path) {
      missingCanonicalPath.push(skill);
      continue;
    }

    const sourceDir = path.resolve(repoRoot, skill.canonical_rel_path);
    if (!await fileExists(sourceDir)) {
      missingSourceDir.push({ skill, sourceDir });
      continue;
    }

    const { policy } = await cache.get(sourceDir, skill);
    const blockedEntry = policy.blockedTargets.find((entry) => entry.agent === agent);
    if (blockedEntry) {
      blocked.push({ skill, reason: blockedEntry.reason });
      continue;
    }

    installable.push(skill);
  }

  return {
    installable,
    blocked,
    missingCanonicalPath,
    missingSourceDir,
  };
}
