import path from "node:path";

import { ensureReadmeSourceRegistry, expectedSkillRenderedHash } from "./attribution.js";
import { getAdapter } from "./adapters.js";
import { managedSkillsForAgent } from "./catalog.js";
import { DistributionPolicyCache, installableSkillsForAgent } from "./distribution.js";
import { copyDir, ensureDir, fileExists, removeDirIfExists } from "./fs.js";
import { writeManagedIndex } from "./indexes.js";
import type { SkillctlCatalog, SkillctlConfig, SyncResult } from "./types.js";
import { syncViaSkillsCli, type SyncProgressCallback } from "./transport.js";

export async function syncCatalog(
  repoRoot: string,
  config: SkillctlConfig,
  catalog: SkillctlCatalog,
  onProgress?: SyncProgressCallback,
): Promise<SyncResult> {
  if (config.transport.mode === "skills-cli") {
    const result = await syncViaSkillsCli(repoRoot, config, catalog, onProgress);
    const cache = new DistributionPolicyCache();
    for (const agent of config.enabledAdapters) {
      const { installable } = await installableSkillsForAgent(repoRoot, catalog, agent, cache);
      await writeManagedIndex(config.stateDir!, agent, installable);
    }
    await ensureReadmeSourceRegistry(repoRoot, catalog);
    return result;
  }

  const copied: SyncResult["copied"] = [];
  const skipped: SyncResult["skipped"] = [];
  const managedIndexesUpdated: SyncResult["managedIndexesUpdated"] = [];
  const cache = new DistributionPolicyCache();

  onProgress?.({ stage: "start", copied: 0 });
  let copiedCount = 0;

  for (const agent of config.enabledAdapters) {
    onProgress?.({ stage: "agent", agent, copied: copiedCount });
    const adapter = getAdapter(agent);
    const installDir = adapter.installDir();
    await ensureDir(installDir);
    const installableSet = await installableSkillsForAgent(repoRoot, catalog, agent, cache);

    for (const skill of managedSkillsForAgent(catalog, agent)) {
      if (skill.visibility !== "public") {
        skipped.push({ agent, skillId: skill.skill_id, reason: "private skill not synced to public agent dirs" });
        continue;
      }
      if (!skill.canonical_rel_path) {
        skipped.push({ agent, skillId: skill.skill_id, reason: "missing canonical path" });
        continue;
      }

      const srcDir = path.resolve(repoRoot, skill.canonical_rel_path);
      if (!await fileExists(srcDir)) {
        skipped.push({ agent, skillId: skill.skill_id, reason: `source missing: ${srcDir}` });
        continue;
      }

      const blocked = installableSet.blocked.find((entry) => entry.skill.skill_id === skill.skill_id);
      if (blocked) {
        await removeDirIfExists(path.join(installDir, skill.skill_id));
        skipped.push({ agent, skillId: skill.skill_id, reason: blocked.reason });
        continue;
      }

      await copyDir(srcDir, path.join(installDir, skill.skill_id));
      await expectedSkillRenderedHash(path.join(installDir, skill.skill_id), skill);
      copied.push({ agent, skillId: skill.skill_id });
      copiedCount += 1;
      onProgress?.({ stage: "skill", agent, skillId: skill.skill_id, copied: copiedCount });
    }

    await writeManagedIndex(config.stateDir!, agent, installableSet.installable);
    managedIndexesUpdated.push(agent);
  }

  await ensureReadmeSourceRegistry(repoRoot, catalog);
  onProgress?.({ stage: "done", copied: copiedCount });

  return { copied, skipped, managedIndexesUpdated };
}
