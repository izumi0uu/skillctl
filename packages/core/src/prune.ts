import fs from "node:fs/promises";
import path from "node:path";

import { getAdapter } from "./adapters.js";
import { managedSkillsForAgent } from "./catalog.js";
import { loadManagedIndex, writeManagedIndex } from "./indexes.js";
import type { PruneResult, SkillctlCatalog, SkillctlConfig } from "./types.js";

export async function pruneManaged(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<PruneResult> {
  void repoRoot;
  const removed: PruneResult["removed"] = [];
  const skipped: PruneResult["skipped"] = [];

  for (const agent of config.enabledAdapters) {
    const adapter = getAdapter(agent);
    const keep = new Set(managedSkillsForAgent(catalog, agent).map((skill) => skill.skill_id));
    const index = await loadManagedIndex(config.stateDir!, agent);

    for (const entry of index.entries) {
      if (keep.has(entry.skill_id)) {
        skipped.push({ agent, skillId: entry.skill_id, reason: "still managed" });
        continue;
      }
      await fs.rm(path.join(adapter.installDir(), entry.skill_id), { recursive: true, force: true });
      removed.push({ agent, skillId: entry.skill_id });
    }

    await writeManagedIndex(config.stateDir!, agent, managedSkillsForAgent(catalog, agent));
  }

  return { removed, skipped };
}
