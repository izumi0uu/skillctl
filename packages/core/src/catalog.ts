import path from "node:path";

import { readJson, writeJson } from "./fs.js";
import { CATALOG_FILE } from "./paths.js";
import { skillctlCatalogSchema } from "./schema.js";
import { inferSkillCategoryFromRelPath } from "./taxonomy.js";
import type { AgentId, CatalogSkill, SkillDescriptor, SkillctlCatalog } from "./types.js";
import { inferSourceKind } from "./skill.js";

export function managedSkillsForAgent(catalog: SkillctlCatalog, agent: AgentId): CatalogSkill[] {
  return catalog.skills.filter((skill) => skill.managed && skill.targets.includes(agent));
}

export function managedSkillIdsForAgent(catalog: SkillctlCatalog, agent: AgentId): string[] {
  return managedSkillsForAgent(catalog, agent).map((skill) => skill.skill_id);
}

export function emptyCatalog(): SkillctlCatalog {
  return {
    version: 1,
    generatedBy: "skillctl",
    skills: [],
  };
}

export async function loadCatalog(repoRoot: string): Promise<SkillctlCatalog> {
  const filePath = path.join(repoRoot, CATALOG_FILE);
  const raw = await readJson<unknown>(filePath);
  return skillctlCatalogSchema.parse(raw);
}

export async function writeCatalog(repoRoot: string, catalog: SkillctlCatalog): Promise<void> {
  const validated = skillctlCatalogSchema.parse(catalog);
  await writeJson(path.join(repoRoot, CATALOG_FILE), validated);
}

export function descriptorToCatalogSkill(repoRoot: string, descriptor: SkillDescriptor, targets: CatalogSkill["targets"]): CatalogSkill {
  const canonicalRelPath = path.relative(repoRoot, descriptor.dirPath);
  return {
    skill_id: descriptor.skillId,
    category: inferSkillCategoryFromRelPath(canonicalRelPath),
    visibility: descriptor.visibility,
    source_kind: inferSourceKind(descriptor.visibility),
    origin_kind: "local-authored",
    hash: descriptor.hash,
    managed: descriptor.managedByDefault,
    targets,
    canonical_rel_path: canonicalRelPath,
  };
}

export function mergeCatalogSkillMetadata(previous: CatalogSkill | undefined, next: CatalogSkill): CatalogSkill {
  if (!previous) {
    return next;
  }

  const originKind = previous.origin_kind === "local-authored" ? next.origin_kind : previous.origin_kind;

  const sourceKind = originKind === "local-authored" ? next.source_kind : inferSourceKind(next.visibility, originKind);

  return {
    ...next,
    display_name: previous.display_name ?? next.display_name,
    category: previous.category ?? next.category,
    tags: previous.tags ?? next.tags,
    source_kind: sourceKind,
    origin_kind: originKind,
    managed: previous.managed,
    enabled: previous.enabled ?? next.enabled,
    targets: previous.targets.length > 0 ? previous.targets : next.targets,
    upstream: originKind === "local-authored" ? next.upstream : previous.upstream ?? next.upstream,
    aliases: previous.aliases ?? next.aliases,
  };
}

// Toggle a skill on/off. Disabling sets enabled=false; enabling clears the flag
// (absence == enabled) to keep the catalog tidy. Returns false if not found.
export function setSkillEnabled(catalog: SkillctlCatalog, skillId: string, enabled: boolean): boolean {
  const skill = catalog.skills.find((entry) => entry.skill_id === skillId);
  if (!skill) {
    return false;
  }
  if (enabled) {
    delete skill.enabled;
  } else {
    skill.enabled = false;
  }
  return true;
}

export function summarizeCatalog(catalog: SkillctlCatalog): { managedSkills: number; publicSkills: number; privateSkills: number; upstreamSkills: number } {
  return {
    managedSkills: catalog.skills.filter((skill) => skill.managed).length,
    publicSkills: catalog.skills.filter((skill) => skill.visibility === "public").length,
    privateSkills: catalog.skills.filter((skill) => skill.visibility === "private").length,
    upstreamSkills: catalog.skills.filter((skill) => skill.origin_kind !== "local-authored").length,
  };
}
