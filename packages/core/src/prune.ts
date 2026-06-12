import fs from "node:fs/promises";
import path from "node:path";

import { getAdapter } from "./adapters.js";
import { loadManagedIndex, writeManagedIndex } from "./indexes.js";
import type { CatalogSkill, PruneResult, SkillctlCatalog, SkillctlConfig } from "./types.js";

function managedSkillsForAgent(catalog: SkillctlCatalog, agent: CatalogSkill["targets"][number]): Set<string> {
  return new Set(catalog.skills.filter((skill) => skill.managed && skill.targets.includes(agent)).map((skill) => skill.skill_id));
}

export async function pruneManaged(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<PruneResult> {
  void repoRoot;
  const removed: PruneResult["removed"] = [];
  const skipped: PruneResult["skipped"] = [];

  for (const agent of config.enabledAdapters) {
    const adapter = getAdapter(agent);
    const keep = managedSkillsForAgent(catalog, agent);
    const index = await loadManagedIndex(config.stateDir!, agent);

    for (const entry of index.entries) {
      if (keep.has(entry.skill_id)) {
        skipped.push({ agent, skillId: entry.skill_id, reason: "still managed" });
        continue;
      }
      await fs.rm(path.join(adapter.installDir(), entry.skill_id), { recursive: true, force: true });
      removed.push({ agent, skillId: entry.skill_id });
    }

    const nextSkills = catalog.skills.filter((skill) => skill.managed && skill.targets.includes(agent));
    await writeManagedIndex(config.stateDir!, agent, nextSkills);
  }

  return { removed, skipped };
}
