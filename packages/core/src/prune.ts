import fs from "node:fs/promises";
import path from "node:path";

import { getAdapter } from "./adapters.js";
import { managedSkillsForAgent } from "./catalog.js";
import { fileExists } from "./fs.js";
import { loadManagedIndex, writeManagedIndex } from "./indexes.js";
import { evaluateSkillDistributionPolicy } from "./portability.js";
import type { PruneResult, SkillctlCatalog, SkillctlConfig } from "./types.js";

export async function pruneManaged(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<PruneResult> {
  const removed: PruneResult["removed"] = [];
  const skipped: PruneResult["skipped"] = [];

  for (const agent of config.enabledAdapters) {
    const adapter = getAdapter(agent);
    const keep = new Set<string>();
    const installable = [];
    for (const skill of managedSkillsForAgent(catalog, agent)) {
      if (!skill.canonical_rel_path) {
        continue;
      }
      const sourceDir = path.resolve(repoRoot, skill.canonical_rel_path);
      if (!await fileExists(sourceDir)) {
        continue;
      }
      const policy = await evaluateSkillDistributionPolicy(sourceDir, skill);
      if (policy.allowedTargets.includes(agent)) {
        keep.add(skill.skill_id);
        installable.push(skill);
      }
    }
    const index = await loadManagedIndex(config.stateDir!, agent);

    for (const entry of index.entries) {
      if (keep.has(entry.skill_id)) {
        skipped.push({ agent, skillId: entry.skill_id, reason: "still managed" });
        continue;
      }
      await fs.rm(path.join(adapter.installDir(), entry.skill_id), { recursive: true, force: true });
      removed.push({ agent, skillId: entry.skill_id });
    }

    await writeManagedIndex(config.stateDir!, agent, installable);
  }

  return { removed, skipped };
}
