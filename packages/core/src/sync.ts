import path from "node:path";

import { ensureReadmeSourceRegistry, expectedSkillRenderedHash } from "./attribution.js";
import { getAdapter } from "./adapters.js";
import { managedSkillsForAgent } from "./catalog.js";
import { copyDir, ensureDir, fileExists } from "./fs.js";
import { writeManagedIndex } from "./indexes.js";
import type { SkillctlCatalog, SkillctlConfig, SyncResult } from "./types.js";
import { syncViaSkillsCli } from "./transport.js";

export async function syncCatalog(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<SyncResult> {
  if (config.transport.mode === "skills-cli") {
    const result = await syncViaSkillsCli(repoRoot, config, catalog);
    for (const agent of config.enabledAdapters) {
      await writeManagedIndex(config.stateDir!, agent, managedSkillsForAgent(catalog, agent));
    }
    await ensureReadmeSourceRegistry(repoRoot, catalog);
    return result;
  }

  const copied: SyncResult["copied"] = [];
  const skipped: SyncResult["skipped"] = [];
  const managedIndexesUpdated: SyncResult["managedIndexesUpdated"] = [];

  for (const agent of config.enabledAdapters) {
    const adapter = getAdapter(agent);
    const installDir = adapter.installDir();
    await ensureDir(installDir);

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

      await copyDir(srcDir, path.join(installDir, skill.skill_id));
      await expectedSkillRenderedHash(path.join(installDir, skill.skill_id), skill);
      copied.push({ agent, skillId: skill.skill_id });
    }

    await writeManagedIndex(config.stateDir!, agent, managedSkillsForAgent(catalog, agent));
    managedIndexesUpdated.push(agent);
  }

  await ensureReadmeSourceRegistry(repoRoot, catalog);

  return { copied, skipped, managedIndexesUpdated };
}
