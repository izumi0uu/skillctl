import path from "node:path";

import { discoverSkillsInRoot } from "./skill.js";
import type { CatalogSkill, SkillConflict, SkillctlCatalog, SkillctlConfig, SourceRoot } from "./types.js";
import { descriptorToCatalogSkill, emptyCatalog, mergeCatalogSkillMetadata } from "./catalog.js";

export interface DiscoverResult {
  catalog: SkillctlCatalog;
  conflicts: SkillConflict[];
}

export async function discoverCatalog(repoRoot: string, config: SkillctlConfig, existingCatalog?: SkillctlCatalog): Promise<DiscoverResult> {
  const rootsByPath = new Map<string, SourceRoot>();
  for (const root of config.sourceRoots) {
    rootsByPath.set(root.path, root);
  }
  for (const privateRoot of config.privateRoots) {
    if (!rootsByPath.has(privateRoot)) {
      rootsByPath.set(privateRoot, {
        path: privateRoot,
        visibility: "private",
        managedByDefault: false,
      });
    }
  }

  const skillMap = new Map<string, CatalogSkill[]>();
  const previousBySkillId = new Map((existingCatalog?.skills ?? []).map((skill) => [skill.skill_id, skill]));

  for (const root of rootsByPath.values()) {
    const descriptors = await discoverSkillsInRoot(root);
    for (const descriptor of descriptors) {
      if (config.excludeSkills.includes(descriptor.skillId)) {
        continue;
      }
      const discovered = descriptorToCatalogSkill(repoRoot, descriptor, config.enabledAdapters);
      const entry = mergeCatalogSkillMetadata(previousBySkillId.get(discovered.skill_id), discovered);
      const bucket = skillMap.get(entry.skill_id) ?? [];
      bucket.push(entry);
      skillMap.set(entry.skill_id, bucket);
    }
  }

  const catalog = emptyCatalog();
  const conflicts: SkillConflict[] = [];

  for (const [skillId, entries] of [...skillMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (entries.length > 1) {
      conflicts.push({
        skillId,
        paths: entries.map((entry) => entry.canonical_rel_path ?? skillId),
      });
      continue;
    }
    catalog.skills.push(entries[0]);
  }

  return { catalog, conflicts };
}
