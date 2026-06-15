import fs from "node:fs/promises";
import path from "node:path";

import { getAdapter } from "./adapters.js";
import { DistributionPolicyCache, installableSkillsForAgent } from "./distribution.js";
import { loadManagedIndex, writeManagedIndex } from "./indexes.js";
import type { AgentId, PruneResult, SkillctlCatalog, SkillctlConfig } from "./types.js";

export type PruneStage = "start" | "agent" | "remove" | "done";
export interface PruneProgressEvent {
  stage: PruneStage;
  agent?: AgentId;
  skillId?: string;
  removed?: number;
}
export type PruneProgressCallback = (event: PruneProgressEvent) => void;

export async function pruneManaged(
  repoRoot: string,
  config: SkillctlConfig,
  catalog: SkillctlCatalog,
  onProgress?: PruneProgressCallback,
): Promise<PruneResult> {
  const removed: PruneResult["removed"] = [];
  const skipped: PruneResult["skipped"] = [];
  const cache = new DistributionPolicyCache();

  onProgress?.({ stage: "start", removed: 0 });
  let removedCount = 0;

  for (const agent of config.enabledAdapters) {
    onProgress?.({ stage: "agent", agent, removed: removedCount });
    const adapter = getAdapter(agent);
    const keep = new Set<string>();
    const installableSet = await installableSkillsForAgent(repoRoot, catalog, agent, cache);
    for (const skill of installableSet.installable) {
      keep.add(skill.skill_id);
    }
    const index = await loadManagedIndex(config.stateDir!, agent);

    for (const entry of index.entries) {
      if (keep.has(entry.skill_id)) {
        skipped.push({ agent, skillId: entry.skill_id, reason: "still managed" });
        continue;
      }
      await fs.rm(path.join(adapter.installDir(), entry.skill_id), { recursive: true, force: true });
      removed.push({ agent, skillId: entry.skill_id });
      removedCount += 1;
      onProgress?.({ stage: "remove", agent, skillId: entry.skill_id, removed: removedCount });
    }

    await writeManagedIndex(config.stateDir!, agent, installableSet.installable);
  }

  onProgress?.({ stage: "done", removed: removedCount });
  return { removed, skipped };
}
